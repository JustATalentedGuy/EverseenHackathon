"""Deterministic numerical contract for exposure-based camera-image heatmaps."""
import unittest

import cv2
import numpy as np

from prototype.heatmap import PresenceHeatmap


class PresenceHeatmapTests(unittest.TestCase):
    def setUp(self):
        self.heat = PresenceHeatmap()
        self.frame = np.full((180, 320, 3), 65, dtype=np.uint8)

    def test_stationary_track_measures_seconds_not_number_of_frames(self):
        for t in [0, .5, 1., 1.5, 2.]:
            self.heat.update(t, {12: (.35, .55)}, self.frame)
        avg, meta = self.heat.snapshot(30)
        self.assertAlmostEqual(meta['person_seconds'], 2)
        self.assertAlmostEqual(meta['elapsed_s'], 2)
        self.assertEqual(meta['coverage_fraction'], 1)
        self.assertAlmostEqual(avg[4, 5], 1.0)
        self.assertAlmostEqual(float(avg.sum()), 1)

    def test_observed_person_time_consistent_at_different_frequencies(self):
        a, b = PresenceHeatmap(), PresenceHeatmap()
        for time_s in [0,1,2,3,4]:
            a.update(time_s,{7:(.2,.3)},self.frame)
        for i in range(21):
            b.update(i/5,{7:(.2,.3)},self.frame)
        self.assertAlmostEqual(a.snapshot(30)[1]['person_seconds'],4)
        self.assertAlmostEqual(b.snapshot(30)[1]['person_seconds'],4)

    def test_two_tracks_contribute_double_exposure(self):
        for t in [0,1,2]:
            self.heat.update(t,{1:(.4,.4),2:(.4,.4)},self.frame)
        avg, meta = self.heat.snapshot(30)
        self.assertEqual(meta['person_seconds'],4)
        self.assertEqual(meta['peak_observed_avg_people_per_tile'],2)
        self.assertEqual(meta['tracked_pairs'],4)

    def test_named_zone_exposure_counts_only_stable_zone_sightings(self):
        self.heat.update(0,{1:(.2,.3)},self.frame,zones={1:'shelf'})
        self.heat.update(1,{1:(.2,.3)},self.frame,zones={1:'shelf'})
        self.heat.update(2,{1:(.2,.3)},self.frame,zones={1:'checkout'})
        self.heat.update(3,{1:(.2,.3)},self.frame,zones={1:'checkout'})
        meta=self.heat.snapshot(30)[1]
        self.assertEqual(meta['person_seconds'],3)
        self.assertEqual(meta['zones_person_seconds'],{'shelf':1.,'checkout':1.})

    def test_identity_loss_does_not_fabricate_unobserved_time(self):
        self.heat.update(0,{1:(.2,.3)},self.frame)
        self.heat.update(1,{2:(.2,.3)},self.frame)
        self.heat.update(2,{},self.frame)
        self.assertEqual(self.heat.snapshot(30)[1]['person_seconds'],0)

    def test_large_gap_is_censored_and_quality_lowers(self):
        self.heat.update(0,{1:(.2,.3)},self.frame)
        self.heat.update(1,{1:(.2,.3)},self.frame)
        self.heat.update(8,{1:(.2,.3)},self.frame)
        self.heat.update(9,{1:(.2,.3)},self.frame)
        avg, meta = self.heat.snapshot(30)
        self.assertAlmostEqual(meta['person_seconds'],2)
        self.assertAlmostEqual(meta['coverage_fraction'],.22,places=2)
        self.assertAlmostEqual(float(avg.sum()), 2/9,places=3)

    def test_window_boundary_prorates_supported_time(self):
        for t in range(35):
            self.heat.update(float(t),{1:(.6,.5)},self.frame)
        avg, meta = self.heat.snapshot(30)
        self.assertEqual(meta['elapsed_s'],30)
        self.assertEqual(meta['person_seconds'],30)
        self.assertAlmostEqual(float(avg.sum()),1)

    def test_valid_jpeg_and_frame_matches_latest_analyzed_frame(self):
        self.heat.update(0,{1:(.4,.4)},self.frame)
        brighter = np.full_like(self.frame,100)
        self.heat.update(1,{1:(.4,.4)},brighter)
        jpg=self.heat.jpeg(30)
        self.assertTrue(jpg.startswith(b'\xff\xd8'))
        rendered=cv2.imdecode(np.frombuffer(jpg,np.uint8),cv2.IMREAD_COLOR)
        self.assertEqual(rendered.shape,brighter.shape)
        self.assertAlmostEqual(int(rendered[0,0,0]),100,delta=5)

    def test_no_observations_and_invalid_windows(self):
        self.assertIsNone(self.heat.jpeg(30))
        self.assertEqual(self.heat.snapshot(30)[1]['person_seconds'],0)
        with self.assertRaises(ValueError):
            self.heat.snapshot(999)


if __name__=='__main__':
    unittest.main()
