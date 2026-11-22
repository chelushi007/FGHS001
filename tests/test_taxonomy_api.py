import unittest
from fastapi.testclient import TestClient
from steelchain.agents.api import app
class TaxonomyApiTests(unittest.TestCase):
 def test_hierarchical_dictionary_and_mapping_are_explicit(self):
  r=TestClient(app).get('/api/v1/categories/taxonomy'); self.assertEqual(r.status_code,200); data=r.json()
  self.assertEqual(len(data['items']),23); self.assertEqual(data['data_origin'],'SIMULATED')
  exact=[x for x in data['legacy_mappings'] if x['mapping_status']=='EXACT']; review=[x for x in data['legacy_mappings'] if x['mapping_status']=='REVIEW_REQUIRED']; unmapped=[x for x in data['legacy_mappings'] if x['mapping_status']=='UNMAPPED']
  self.assertEqual(len(exact),1); self.assertEqual(len(review),19); self.assertEqual(len(unmapped),0); self.assertTrue(all(x['taxonomy_id'] is not None for x in review))
if __name__=='__main__': unittest.main()
