from __future__ import annotations
import copy, json
from pathlib import Path
import sys, unittest
from jsonschema import Draft202012Validator, FormatChecker
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'src'))
from infocs.dedupe.core import DuplicateConflictError, ObservationStatus, dedupe, reconcile
from infocs.diff.core import content_hash, diff
from infocs.identity.core import canonical_url, identify
from infocs.models import DataValidationError, RecordCandidate
F=ROOT/'tests'/'fixtures'
def load(name):
 p=json.loads((F/name).read_text(encoding='utf-8'))
 p.pop('id',None)
 t=p.get('technical')
 if t is not None:
  t.pop('content_hash',None); t.pop('identity_strategy',None)
  if not t: p.pop('technical',None)
 return p
class IdentityAndChangeTests(unittest.TestCase):
 def test_identity_priority_and_title_change(self):
  r=load('record_procurement_valid.json'); a=identify(r); r['title']='Título corregido'; self.assertEqual(a.record_id,identify(r).record_id); self.assertEqual(a.strategy,'official_id')
 def test_case_url_and_fingerprint_fallbacks(self):
  r=load('record_minimal_valid.json'); r['source'].pop('official_id',None); r['procurement']={'expediente':'CASE 9'}; self.assertEqual(identify(r).strategy,'case_number'); r.pop('procurement'); self.assertEqual(identify(r).strategy,'canonical_url'); r.pop('source_url'); self.assertEqual(identify(r).strategy,'composite_fingerprint')
 def test_source_namespace_and_url_rules(self):
  a=load('record_minimal_valid.json'); b=copy.deepcopy(a); b['source']['id']='other_source'; self.assertNotEqual(identify(a).record_id,identify(b).record_id); self.assertEqual(canonical_url('HTTPS://EXAMPLE.TEST/a/#x?utm_x=y'),'https://example.test/a')
 def test_hash_ignores_check_time_order_sets_and_decimal_form(self):
  a=load('contract_v3_awardee_changed.json'); a['procurement']['awardee']['name']='Servicios Ficticios del Levante SL'; a['tags']=['a','b']; b=load('contract_same_semantics_different_order.json'); self.assertEqual(content_hash(a),content_hash(b))
 def test_hash_changes_for_title_amount_and_awardee(self):
  a=load('contract_v3_awardee_changed.json'); b=copy.deepcopy(a); b['title']='otro'; self.assertNotEqual(content_hash(a),content_hash(b)); b=load('contract_v2_amount_changed.json'); self.assertNotEqual(content_hash(a),content_hash(b))
 def test_diff_paths(self):
  a=load('contract_v3_awardee_changed.json'); b=load('contract_v2_amount_changed.json'); paths={x.path for x in diff(a,b)}; self.assertIn('financial.award_amount.value',paths); self.assertIn('procurement.awardee.name',paths)
 def test_dedupe_conflict_and_identical(self):
  a=load('contract_v3_awardee_changed.json'); self.assertEqual(len(dedupe([a,copy.deepcopy(a)])),1); b=copy.deepcopy(a); b['title']='conflict'; self.assertRaises(DuplicateConflictError,dedupe,[a,b])
 def test_events_create_update_missing_failed_and_reappeared(self):
  a=load('contract_v3_awardee_changed.json'); state,ev=reconcile({},[a],ObservationStatus.COMPLETE_SUCCESS,source_id='fixture_procurement',checked_at='2026-09-23T09:15:00Z'); self.assertEqual(ev[0].type,'create'); changed=load('contract_v2_amount_changed.json'); state,ev=reconcile(state,[changed],ObservationStatus.COMPLETE_SUCCESS,source_id='fixture_procurement',checked_at='2026-09-24T09:15:00Z'); self.assertEqual(ev[0].type,'update'); state,ev=reconcile(state,[],ObservationStatus.FAILED,source_id='fixture_procurement',checked_at='2026-09-25T09:15:00Z'); self.assertEqual(ev,()); state,ev=reconcile(state,[],ObservationStatus.COMPLETE_SUCCESS,source_id='fixture_procurement',checked_at='2026-09-26T09:15:00Z'); self.assertEqual(ev[0].type,'missing_from_source'); state,ev=reconcile(state,[changed],ObservationStatus.COMPLETE_SUCCESS,source_id='fixture_procurement',checked_at='2026-09-27T09:15:00Z'); self.assertEqual(ev[0].type,'reappeared')
 def test_event_schema_accepts_generated_event(self):
  record=load('contract_v3_awardee_changed.json'); _, events=reconcile({},[record],ObservationStatus.COMPLETE_SUCCESS,source_id='fixture_procurement',checked_at='2026-09-23T09:15:00Z'); schema=json.loads((ROOT/'schemas'/'event.schema.json').read_text(encoding='utf-8')); Draft202012Validator(schema,format_checker=FormatChecker()).validate(events[0].to_dict())
 def test_admin_mismatch_and_naive_timestamp_rejected(self):
  p=load('record_minimal_valid.json'); p['authority']['administration_level']='state'; self.assertRaises(DataValidationError,RecordCandidate.from_dict,p); p=load('record_minimal_valid.json'); p['dates']['detected_at']='2026-09-21T10:00:00'; self.assertRaises(DataValidationError,RecordCandidate.from_dict,p)
