import json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from registration import register, manual_register, RegistrationError, evaluate
from cpm_core import compare_photos

class TestRegistration(unittest.TestCase):
    def test_sift_features_reused_only_within_registration(self):
        rng = np.random.default_rng(123)
        ref = rng.integers(0, 256, (240, 320), dtype=np.uint8)
        mov = cv2.warpAffine(ref, np.float32([[1, 0, 17], [0, 1, 9]]), (320, 240))
        real_factory = cv2.SIFT_create
        detections = []

        class CountingSIFT:
            def __init__(self, *args, **kwargs):
                self.detector = real_factory(*args, **kwargs)

            def detectAndCompute(self, image, mask):
                keypoints, descriptors = self.detector.detectAndCompute(image, mask)
                detections.append((image, descriptors, descriptors.copy()))
                return keypoints, descriptors

        with patch('registration.cv2.SIFT_create', side_effect=CountingSIFT) as factory:
            for call in range(2):
                H, *rest = register(ref, mov, nfeatures=1000)
                self.assertEqual(len(detections), 2 * (call + 1))
                self.assertEqual(factory.call_count, call + 1)
                factory.assert_called_with(nfeatures=1000, contrastThreshold=.015)
                self.assertIs(detections[-2][0], ref)
                self.assertIs(detections[-1][0], mov)
                self.assertLess(np.linalg.norm(H[:2, 2] - [-17, -9]), 2)
                diagnostics = rest[-1]
                self.assertTrue(diagnostics['selected']['accepted'])
                self.assertEqual(
                    [(d['method'], d['ratio_test'], d['model']) for d in diagnostics['candidates']],
                    [(method, ratio, model)
                     for method in ('SIFT', 'RootSIFT', 'AKAZE')
                     for ratio in (.75, .85, .9)
                     for model in ('affine', 'homography')],
                )
        for _, descriptors, original in detections:
            np.testing.assert_array_equal(descriptors, original)

    def test_insufficient_features_preserves_each_method_diagnostic(self):
        blank = np.zeros((240, 320), dtype=np.uint8)
        with self.assertRaises(RegistrationError) as error:
            register(blank, blank)
        diagnostics = error.exception.diagnostics['candidates']
        self.assertEqual([d['method'] for d in diagnostics], ['SIFT', 'RootSIFT', 'AKAZE'])
        for diagnostic in diagnostics:
            self.assertFalse(diagnostic['accepted'])
            self.assertEqual(diagnostic['reasons'], ['特征不足'])

    def test_unavailable_sift_preserves_diagnostics_and_akaze_fallback(self):
        rng = np.random.default_rng(123)
        ref = rng.integers(0, 256, (240, 320), dtype=np.uint8)
        mov = cv2.warpAffine(ref, np.float32([[1, 0, 17], [0, 1, 9]]), (320, 240))
        for unavailable in (None, cv2.error('disabled'), AttributeError('disabled'), NotImplementedError('disabled')):
            with self.subTest(unavailable=unavailable):
                replacement = {'new': None} if unavailable is None else {'side_effect': unavailable}
                with patch('registration.cv2.SIFT_create', **replacement):
                    H, *rest = register(ref, mov)
                diagnostics = rest[-1]
                self.assertEqual(len(diagnostics['candidates']), 8)
                self.assertEqual([d['method'] for d in diagnostics['candidates'][:2]], ['SIFT', 'RootSIFT'])
                for diagnostic in diagnostics['candidates'][:2]:
                    self.assertFalse(diagnostic['accepted'])
                    self.assertIn('SIFT_create', diagnostic['reasons'][0])
                self.assertEqual(diagnostics['selected']['method'], 'AKAZE')
                self.assertTrue(diagnostics['selected']['accepted'])
                self.assertLess(np.linalg.norm(H[:2, 2] - [-17, -9]), 2)

    def test_affine_and_change(self):
        rng=np.random.default_rng(123);a=rng.integers(0,256,(360,480),dtype=np.uint8)
        A=np.float32([[1,0,17],[0,1,9]]);b=cv2.warpAffine(a,A,(480,360));b[140:190,160:225]=50
        H,*rest=register(a,b)
        self.assertTrue(rest[-1]['selected']['accepted']);self.assertLess(np.linalg.norm(H[:2,2]-[-17,-9]),2)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);cv2.imwrite(str(p/'a.png'),a);cv2.imwrite(str(p/'b.png'),b)
            r=compare_photos(str(p/'a.png'),str(p/'b.png'),str(p/'out'),registration='auto')
            self.assertGreater(r['stats']['changed_pixel_ratio'],0)
            self.assertTrue(r['registration']['selected']['accepted'])
    def test_unrelated_rejected(self):
        rng=np.random.default_rng(44);a=rng.integers(0,256,(240,320),dtype=np.uint8);b=rng.integers(0,256,(240,320),dtype=np.uint8)
        with self.assertRaises(RegistrationError): register(a,b)
    def test_degenerate_rejected(self):
        pts=np.float32([[x,y] for x in range(20,240,50) for y in range(20,200,40)])
        H=np.diag([.001,.001,1.]);d=evaluate(H,np.ones(len(pts)),pts,pts,(240,320),(240,320),3,'test','homography')
        self.assertFalse(d['accepted'])
    def test_manual_independent_check(self):
        a=np.zeros((300,400),np.uint8)
        fit=[[x,y] for x,y in [(.1,.1),(.5,.1),(.9,.1),(.1,.5),(.9,.5),(.1,.9),(.5,.9),(.9,.9)]]
        check=[[.3,.3],[.7,.3],[.3,.7],[.7,.7]]
        data={'fit':[[p,p] for p in fit],'check':[[p,p] for p in check]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'p.json';p.write_text(json.dumps(data));self.assertTrue(manual_register(p,a,a)[-1]['selected']['accepted'])
            data['check'][0]=[check[0],[.5,.4]];p.write_text(json.dumps(data))
            with self.assertRaises(RegistrationError):manual_register(p,a,a)
    def test_real_pair_safe_fallback(self):
        a=cv2.imread(str(ROOT/'data/before.jpg'),0);b=cv2.imread(str(ROOT/'data/after.jpg'),0)
        with self.assertRaises(RegistrationError) as e: register(a,b)
        self.assertEqual(len(e.exception.diagnostics['candidates']),18)
if __name__=='__main__': unittest.main()
