"""Operator-drawn retail layout, camera-zone synthesis, and guarded topology cues.

Coordinates represent a *schematic* layout, not surveyed floor geometry. A
camera-zone link is explicitly configured by the user. Never sum possibly
overlapping camera views and call the total unique people.
"""
from collections import deque
import re

COLS, ROWS = 12, 8
ROLES = {'entrance', 'exit', 'checkout', 'aisle', 'display', 'other'}
MAX_SECTIONS = 120


def validate_layout(layout, config):
    if not isinstance(layout, dict) or not isinstance(layout.get('sections'), list):
        raise ValueError('Provide an object containing sections')
    if len(layout['sections']) > MAX_SECTIONS:
        raise ValueError(f'Maximum {MAX_SECTIONS} schematic sections')
    available = {(c['id'],z['id']) for c in config.get('cameras', []) for z in c.get('zones',[])}
    found=set()
    mapped=set()
    for s in layout['sections']:
        if not isinstance(s,dict): raise ValueError('Each section must be an object')
        sid=s.get('id')
        if not isinstance(sid,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,56}',sid) or sid in found:
            raise ValueError('Section identifiers must be unique and use letters/digits/-/_')
        found.add(sid)
        if not isinstance(s.get('name'),str) or not 1<=len(s['name'].strip())<=80:
            raise ValueError('Each section needs a name (1–80 characters)')
        if s.get('role','other') not in ROLES: raise ValueError('Unknown section role')
        vals=[s.get(k) for k in ('x','y','w','h')]
        if any(type(v)!=int for v in vals):raise ValueError('Grid dimensions must be integers')
        x,y,w,h=vals
        if x<0 or y<0 or w<1 or h<1 or x+w>COLS or y+h>ROWS:
            raise ValueError('Section extends outside the floor grid')
        links=s.get('links',[])
        if not isinstance(links,list) or len(links)>256:
            raise ValueError('Invalid camera-zone links')
        used=set()
        for link in links:
            if not isinstance(link,dict):raise ValueError('Invalid camera-zone mapping')
            key=(link.get('camera_id'), link.get('zone_id'))
            if key not in available:raise ValueError('Unknown camera-zone mapping: '+str(key))
            if key in used:raise ValueError('Repeated camera-zone mapping')
            if key in mapped:raise ValueError('One camera zone cannot represent two schematic sections')
            used.add(key)
            mapped.add(key)
    rects=layout['sections']
    for i,a in enumerate(rects):
        for b in rects[i+1:]:
            if (a['x']<b['x']+b['w'] and b['x']<a['x']+a['w'] and
                a['y']<b['y']+b['h'] and b['y']<a['y']+a['h']):
                raise ValueError(f'Sections overlap: {a["name"]}, {b["name"]}')
    return layout


def neighbors(a,b):
    """Adjacent iff rectangles share a positive-length side (not a corner)."""
    horizontal=(a['x']+a['w']==b['x'] or b['x']+b['w']==a['x']) and max(a['y'],b['y'])<min(a['y']+a['h'],b['y']+b['h'])
    vertical=(a['y']+a['h']==b['y'] or b['y']+b['h']==a['y']) and max(a['x'],b['x'])<min(a['x']+a['w'],b['x']+b['w'])
    return horizontal or vertical


def build_topology(sections):
    """Build an internal undirected physical adjacency plus back-to-front path.

    Operator role assignments trump automatic bottom/top role inference.
    Without explicit entrances and exits, bottom-edge and top-edge tiles are
    used as schematic assumptions, made visible in returned metadata.
    """
    nodes={s['id']:s for s in sections}
    edges={sid:[] for sid in nodes}
    for i,a in enumerate(sections):
        for b in sections[i+1:]:
            if neighbors(a,b):
                edges[a['id']].append(b['id']);edges[b['id']].append(a['id'])
    explicit_start=[s['id'] for s in sections if s.get('role')=='entrance']
    explicit_end=[s['id'] for s in sections if s.get('role')=='exit']
    starts=explicit_start or [s['id'] for s in sections if s['y']+s['h']==ROWS]
    ends=explicit_end or [s['id'] for s in sections if s['y']==0]
    # Forward edges lead towards the back; same-row connections work both ways.
    forward={a:[] for a in nodes}
    for a, nb in edges.items():
        for b in nb:
            middle_a=nodes[a]['y']+nodes[a]['h']/2
            middle_b=nodes[b]['y']+nodes[b]['h']/2
            if middle_b<=middle_a:
                forward[a].append(b)
    routes=[]
    for start in starts:
        queue=deque([[start]]); visited={start}
        while queue:
            route=queue.popleft()
            if route[-1] in ends and len(route)>1:
                routes.append(route);break
            for next_id in forward[route[-1]]:
                if next_id not in visited:
                    visited.add(next_id);queue.append(route+[next_id])
    centrality={n:sum(n in route[1:-1] for route in routes) for n in nodes}
    return {'adjacency':edges,'forward':forward,'entrances':starts,'exits':ends,
            'assumed_entrances':not bool(explicit_start), 'assumed_exits':not bool(explicit_end),
            'routes':routes,'route_through_count':centrality,
            'disconnected':[n for n in nodes if not edges[n]],
            'note':'Internal schematic graph. Adjacent touching tiles are treated as connected; blocked aisles/walls need manual review.'}


def aggregate(layout, config, status):
    cams={c['id']:c for c in status.get('cameras',[])}
    zone_labels={(c['id'],z['id']):z.get('label',z['id']) for c in config.get('cameras',[]) for z in c.get('zones',[])}
    data=[]
    for s in layout['sections']:
        evidence=[]
        for link in s.get('links',[]):
            cid,zid=link['camera_id'],link['zone_id']
            cam=cams.get(cid)
            if not cam:continue
            zone=next((z for z in cam.get('zones',[]) if z['id']==zid),None)
            if not zone:continue
            health=cam.get('measurement',{})
            evidence.append({'camera_id':cid, 'zone_id':zid,
                             'zone_label':zone_labels.get((cid,zid),zid),
                             'fresh':bool(health.get('fresh')),
                             'state':health.get('state','no_data'),
                             'elapsed_s':cam.get('elapsed_s',0),
                             'occupancy':zone.get('occupancy'),
                             'mean_5m':zone.get('mean_occupancy_5m',0),
                             'p90_5m':zone.get('p90_occupancy_5m',0),
                             'samples_5m':zone.get('samples_5m',0),
                             'dwell_s':zone.get('partial_dwell_mean_s',0),
                             'dwell_tracks':zone.get('partial_dwell_tracks',0),
                             'track_entries':zone.get('observed_track_entries',0),
                             'review':next((r for r in cam.get('inspection_cues',[]) if r.get('zone')==zid),None)})
        fresh=[e for e in evidence if e['fresh'] and e['occupancy'] is not None]
        # Max is safer than summing unsynchronized or overlapping cameras.
        n=max([e['occupancy'] for e in fresh],default=None)
        # We do NOT sum track counts, dwell, or entrance visits across cameras.
        high=max(fresh,key=lambda z:(z['occupancy'],z['samples_5m'])) if fresh else None
        readable=bool(fresh)
        data.append({'id':s['id'],'name':s['name'],'role':s.get('role','other'),
                     'x':s['x'],'y':s['y'],'w':s['w'],'h':s['h'],
                     'count':n,'mean_5m':max([e['mean_5m'] for e in fresh],default=None),
                     'p90_5m':max([e['p90_5m'] for e in fresh],default=None),
                     'partial_dwell_s':high['dwell_s'] if high else None,
                     'observed_tracks':high['track_entries'] if high else None,
                     'samples_5m':max([e['samples_5m'] for e in fresh],default=0),
                     'active_feeds':len(fresh),'mapped_feeds':len(evidence),
                     'configured_links':len(s.get('links',[])),
                     'source_zone':{'camera_id':high['camera_id'],'zone_id':high['zone_id']} if high else None,
                     'review_evidence':[e['review'] for e in fresh if e['review']],
                     'state':'observing' if readable else 'no_live_evidence',
                     'sources':evidence})
    return data


def insights(sections, topology):
    """Specific, operator-actionable **hypotheses**, not causal diagnoses."""
    cues=[]
    verified={s['id']:s for s in sections if s['state']=='observing' and s['samples_5m']>=10
              and any(e.get('elapsed_s',0)>=20 and e.get('state')=='observing'
                      for e in s.get('sources',[]))}
    stressed=[s for s in verified.values() if s['review_evidence']]
    # No confirmed dead zone merely because it has never been measured.
    underused=[s for s in verified.values() if s['count']==0 and
               s['mean_5m'] is not None and s['mean_5m']<=.5 and not s['review_evidence']]
    def graph_distance(start,end):
        if start==end:return 0
        checked={start};queue=deque([(start,0)])
        while queue:
            node,distance=queue.popleft()
            for nxt in topology['adjacency'].get(node,[]):
                if nxt==end:return distance+1
                if nxt not in checked:
                    checked.add(nxt);queue.append((nxt,distance+1))
        return None
    for busy in stressed:
        options=[a for a in underused if a['id']!=busy['id'] and a['role'] not in ('entrance','exit','checkout')
                 and graph_distance(busy['id'],a['id']) is not None]
        options.sort(key=lambda a:(graph_distance(busy['id'],a['id']),a['name']))
        evidence=busy['review_evidence'][0]
        if options:
            alt=options[0]
            cues.append({'kind':'redistribution_candidate','severity':'review',
                         'section_id':busy['id'],'candidate_id':alt['id'],
                         'title':f'Consider redistributing activity from {busy["name"]}',
                         'recommendation':f'Inspect whether a movable display or activity from {busy["name"]} could be trialled in {alt["name"]}. Verify access and customer paths first.',
                         'evidence':f'{busy["name"]}: {busy["count"]} observed now with a sustained camera review cue; {alt["name"]}: 0 observed now and mean {alt["mean_5m"]:.2f} over {alt["samples_5m"]} samples.',
                         'caveat':'A low-use section is not proven unused; this is not evidence that physically swapping whole departments will help.'})
        else:
            cues.append({'kind':'inspection','severity':'review','section_id':busy['id'],
                         'title':f'Review sustained activity at {busy["name"]}',
                         'recommendation':'Inspect staff access, aisle clearance and camera occlusion; insufficient verified low-use alternative for a swap suggestion.',
                         'evidence':evidence.get('reason','Repeated elevated camera-zone occupancy'),
                         'caveat':'No verified destination was observed.'})
    for s in sections:
        paths=topology['route_through_count'].get(s['id'],0)
        if paths and s['id'] in verified and not s['review_evidence'] and paths>=2:
            cues.append({'kind':'topology_watch','severity':'info','section_id':s['id'],
                         'title':f'Possible passage concentration: {s["name"]}',
                         'recommendation':'Check whether the drawn plan represents actual open walkways; monitor this junction before altering displays.',
                         'evidence':f'This schematic node lies on {paths} computed entrance-to-back routes.',
                         'caveat':'Graph routes are geometric assumptions, not tracked customer paths.'})
    if topology['disconnected']:
        cues.append({'kind':'layout_gap','severity':'info','section_id':None,
                     'title':'Disconnected layout sections',
                     'recommendation':'Place sections edge-to-edge, or correct the schematic if gaps represent corridors.',
                     'evidence':f'{len(topology["disconnected"])} section(s) have no adjacent tile.',
                     'caveat':'The topology cannot infer traversability through walls or unmodelled corridors.'})
    return cues


def full_report(layout,config,status):
    sect=aggregate(layout,config,status)
    graph=build_topology(layout['sections'])
    observed=[s for s in sect if s['count'] is not None]
    return {'sections':sect,'topology':graph,'insights':insights(sect,graph),
            'overall':{'sections':len(sect),'observed_sections':len(observed),
                       'cameras_configured':len(config.get('cameras',[])),
                       'cameras_live':sum(c.get('measurement',{}).get('fresh',False) for c in status.get('cameras',[])),
                       'visible_section_count_sum':sum(s['count'] for s in observed),
                       'note':'Section count sum is NOT unique people: mapped camera views and physical areas may overlap. A section uses the maximum fresh camera-zone occupancy, not a sum.'},
            'note':'Camera zones require explicit mapping; no cross-camera identity fusion, validated customer journeys, or automatic causal bottleneck labels.'}
