from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import re
import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.ndimage import gaussian_filter, maximum_filter

def validate_polygon(points):
    p = np.asarray(points, dtype=np.float32)
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < 3 or not np.isfinite(p).all():
        raise ValueError('A zone requires at least three finite points')
    if np.any(p < 0) or np.any(p > 1): raise ValueError('Use normalized image coordinates in [0,1]')
    if abs(cv2.contourArea(p)) < 1e-5: raise ValueError('Zone has zero area')
    def cross(a,b,c): return float(np.cross(b-a,c-a))
    for i in range(len(p)):
        for j in range(i+1,len(p)):
            if j == i+1 or (i == 0 and j == len(p)-1): continue
            a,b,c,d = p[i],p[(i+1)%len(p)],p[j],p[(j+1)%len(p)]
            bounds_overlap = np.all(np.maximum(np.minimum(a,b),np.minimum(c,d)) <= np.minimum(np.maximum(a,b),np.maximum(c,d)))
            if bounds_overlap and cross(a,b,c)*cross(a,b,d) <= 0 and cross(c,d,a)*cross(c,d,b) <= 0:
                raise ValueError('Zone edges intersect; redraw the polygon')
    return p

def validate_config(config):
    if config.get('schema_version') != 1: raise ValueError('Expected schema_version 1')
    cams = config.get('cameras', [])
    if not cams: raise ValueError('At least one camera is required')
    ids = [c.get('id') for c in cams]
    if any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',x) for x in ids) or len(ids) != len(set(ids)):
        raise ValueError('Camera IDs must be unique and contain letters, numbers, underscores or dashes')
    if any(x not in ids for x in config.get('zone_owners',{}).values()): raise ValueError('Unknown zone owner camera')
    for c in cams:
        if not isinstance(c.get('source'),str) or not c['source']: raise ValueError('Camera source is required')
        names = set()
        for z in c.get('zones', []):
            if not z.get('id') or z['id'] in names: raise ValueError('Zone IDs must be unique per camera')
            names.add(z['id']); validate_polygon(z['polygon'])
            if z.get('owner_camera',c['id']) not in ids: raise ValueError('Unknown owner camera')
        if c.get('calibration'):
            c['calibration'] = fit_calibration(c['calibration'])
    return config

def signed_distance(point, polygon):
    return cv2.pointPolygonTest(np.asarray(polygon,np.float32),tuple(map(float,point)),True)

def assign_zone(point, zones):
    hits = [(z.get('priority',0),z['id']) for z in zones if signed_distance(point,z['polygon']) >= 0]
    if not hits: return None
    hits.sort(reverse=True)
    if len(hits)>1 and hits[0][0] == hits[1][0]: return None  # explicit ambiguity
    return hits[0][1]

def project(h, points):
    p = np.asarray(points,float).reshape(-1,2)
    q = np.column_stack([p,np.ones(len(p))]) @ np.asarray(h,float).T
    if np.any(abs(q[:,2])<1e-8): raise ValueError('Point is near the homography horizon')
    return q[:,:2]/q[:,2,None]

def fit_calibration(cal):
    image = np.asarray(cal['image_points'],float); world=np.asarray(cal['world_points'],float)
    if image.shape != world.shape or image.ndim != 2 or image.shape[1] != 2 or len(image)<6:
        raise ValueError('Provide >=6 corresponding floor points: 4 fit and >=2 independent checks')
    if not np.isfinite(image).all() or not np.isfinite(world).all(): raise ValueError('Invalid calibration points')
    if np.any(image<0) or np.any(image>1): raise ValueError('Image anchors must be normalized')
    if abs(cv2.contourArea(cv2.convexHull(image[:4].astype(np.float32)))) < 0.005:
        raise ValueError('Floor anchors are too concentrated or collinear')
    if np.linalg.matrix_rank(world[:4]-world[0]) < 2: raise ValueError('World anchors are collinear')
    h,_=cv2.findHomography(image[:4],world[:4],0)
    if h is None: raise ValueError('Cannot fit floor homography')
    errors=np.linalg.norm(project(h,image[4:])-world[4:],axis=1)
    limit=float(cal.get('max_check_error_m',0.3))
    if not 0<limit<=1: raise ValueError('Check-error limit must be >0 and <=1m')
    if max(errors)>limit: raise ValueError(f'Independent floor check failed: {max(errors):.3f}m > {limit:.3f}m')
    return {**cal,'homography':h.tolist(),'check_errors_m':errors.tolist(),
            'valid_polygon':cv2.convexHull(image[:4].astype(np.float32)).reshape(-1,2).tolist(),
            'status':'checked'}

def world_point(point,cal):
    if not cal or cal.get('status')!='checked': return None
    if signed_distance(point,cal['valid_polygon'])<0: return None
    return project(cal['homography'],[point])[0].tolist()

def projection_sigma(point,cal,shape,pixel_sigma=2):
    """Local projection sensitivity plus independent-check residual; approximate bound."""
    p=np.array(point,float); h,w=shape
    offsets=np.array([[pixel_sigma/w,0],[-pixel_sigma/w,0],[0,pixel_sigma/h],[0,-pixel_sigma/h]])
    q=project(cal['homography'],p+offsets); centre=project(cal['homography'],[p])[0]
    sensitivity=float(np.max(np.linalg.norm(q-centre,axis=1)))
    return sensitivity+max(cal.get('check_errors_m',[0]))

class ZoneState:
    """Timestamp persistence with a boundary margin; abstain at ambiguous overlaps."""
    def __init__(self, zones, persistence_s=0.2, margin=0.008):
        self.zones=zones; self.persistence=persistence_s; self.margin=margin; self.states={}
    def update(self,tid,t,point):
        s=self.states.setdefault(tid,{'zone':None,'pending':None,'since':t,'last':t})
        if t < s['last']: raise ValueError('Nonmonotonic timestamps')
        if t-s['last']>1.0: s.update(zone=None,pending=None,since=t)
        s['last']=t
        candidate=assign_zone(point,self.zones)
        hits=sorted([z.get('priority',0) for z in self.zones if signed_distance(point,z['polygon'])>=0],reverse=True)
        if len(hits)>1 and hits[0]==hits[1]:
            s.update(zone=None,pending=None,since=t)
            return None
        old=next((z for z in self.zones if z['id']==s['zone']),None)
        if old and signed_distance(point,old['polygon'])>=-self.margin:
            candidate=s['zone']
        if candidate==s['zone']:
            s.update(pending=None,since=t); return s['zone']
        if candidate!=s['pending']:
            s.update(pending=candidate,since=t)
        if t-s['since']+1e-9>=self.persistence:
            s.update(zone=candidate,pending=None,since=t)
        return s['zone']

class Analytics:
    """Observed dwell is accrued only between consecutive reliable observations."""
    def __init__(self,zones,persistence_s=0.2,margin=0.008,max_gap_s=0.45):
        self.zone_state=ZoneState(zones,persistence_s,margin); self.max_gap=max_gap_s
        self.last={}; self.observed_dwell=defaultdict(float); self.transitions=[]; self.censored=set()
    def update(self,tid,t,point):
        z=self.zone_state.update(tid,t,point); previous=self.last.get(tid)
        if previous:
            pt,pz=previous; dt=t-pt
            if 0<=dt<=self.max_gap and pz==z and z is not None:
                self.observed_dwell[(tid,z)]+=dt
            elif dt>self.max_gap: self.censored.add(tid)
            elif z!=pz and pz is not None and z is not None:
                self.transitions.append({'track_id':str(tid),'from':pz,'to':z,'time':t})
        else: self.censored.add(tid)  # first sighting is not a proven arrival
        self.last[tid]=(t,z); return z
    def snapshot(self):
        return {'observed_dwell': [{'track_id':str(k[0]),'zone':k[1],'seconds':v,'partial':True}
                                   for k,v in self.observed_dwell.items()],
                'transitions':self.transitions,
                'note':'Observed intervals only; missing time and blind gaps are excluded. Track IDs are camera-scoped.'}

def propose_zones(points, grid=64, min_support=10):
    """Behavior heat regions, not inferred store semantics. No labels used."""
    p=np.asarray(points,float).reshape(-1,2)
    p=p[np.isfinite(p).all(axis=1)&(p>=0).all(axis=1)&(p<=1).all(axis=1)]
    if len(p)<min_support: return []
    h,_,_=np.histogram2d(p[:,1],p[:,0],bins=grid,range=[[0,1],[0,1]])
    smooth=gaussian_filter(h,2)
    mask=(smooth>max(float(smooth.max())*0.15,0.02)).astype(np.uint8)
    count,labels,stats,centroids=cv2.connectedComponentsWithStats(mask)
    proposals=[]
    for i in range(1,count):
        x,y,w,hh,area=stats[i]
        support=int(h[labels==i].sum())
        if area<12 or support<min_support: continue
        proposals.append({'id':f'activity_{i}','label':'Activity region — confirm meaning',
                          'polygon':[[x/grid,y/grid],[(x+w)/grid,y/grid],[(x+w)/grid,(y+hh)/grid],[x/grid,(y+hh)/grid]],
                          'support':support,'approved':False})
    return sorted(proposals,key=lambda z:-z['support'])[:6]

def select_review_frames(records,budget):
    """Pick disagreement/uncertain frames with temporal diversity, without GT."""
    candidates=[]
    for r in records:
        det=np.asarray(r['detections'],float).reshape(-1,6)
        weak=int(((det[:,4]>=0.1)&(det[:,4]<0.5)).sum()) if len(det) else 0
        counts=r.get('augmented_count',len(det))
        score=weak+2*abs(int(counts)-len(det))+int(len(det)==0)
        candidates.append((score,r['name'],r['frame']))
    chosen=[]; times=defaultdict(list)
    for score,name,f in sorted(candidates,reverse=True):
        if all(abs(f-other)>=50 for other in times[name]):
            chosen.append({'name':name,'frame':f,'priority':score}); times[name].append(f)
        if len(chosen)>=budget: break
    return chosen

def iou_matrix(a,b):
    a=np.asarray(a,float).reshape(-1,4); b=np.asarray(b,float).reshape(-1,4)
    if not len(a) or not len(b): return np.zeros((len(a),len(b)))
    inter=np.prod(np.maximum(0,np.minimum(a[:,None,2:],b[None,:,2:])-np.maximum(a[:,None,:2],b[None,:,:2])),axis=2)
    aa=np.prod(np.maximum(0,a[:,2:]-a[:,:2]),axis=1); bb=np.prod(np.maximum(0,b[:,2:]-b[:,:2]),axis=1)
    return inter/np.maximum(aa[:,None]+bb[None,:]-inter,1e-9)

def match_boxes(gt,pred,threshold=0.5):
    iou=iou_matrix(gt,pred)
    if not iou.size: return []
    # Optimize admissible match cardinality first; disallow subthreshold edges.
    cost=np.where(iou>=threshold,-1-iou,1000.)
    a,b=linear_sum_assignment(cost)
    return [(int(i),int(j)) for i,j in zip(a,b) if iou[i,j]>=threshold]

def conservative_zone_total(camera_counts,owner_camera=None):
    if owner_camera:
        if owner_camera not in camera_counts: return {'value':None,'mode':'owner unavailable'}
        return {'value':camera_counts[owner_camera],'mode':'owner-view observed count'}
    return {'value':None,'lower_bound':max(camera_counts.values(),default=0),
            'upper_bound':sum(camera_counts.values()),'mode':'duplicate uncertainty interval for observed detections'}
