"""PostgreSQL business dispatch receipts. No parallel workflow state machine."""
import copy
from psycopg.types.json import Jsonb
from .contracts import digest
from .business_contract import BusinessContractError


class BusinessStore:
    def __init__(self, db):
        self.db = db

    def get(self, scope, operation, request_id):
        return self.db.execute('SELECT * FROM mc_business_operations WHERE scope_sha256=%s AND operation=%s AND request_id=%s',
                               (digest(scope), operation, request_id)).fetchone()

    def unresolved(self, resource):
        return self.db.execute("SELECT * FROM mc_business_operations WHERE resource_key=%s AND state IN ('claimed','dispatched','outcome_unknown') ORDER BY created_at LIMIT 1", (resource,)).fetchone()

    def claim(self, scope, operation, request_id, fingerprint, request, resource, domain):
        with self.db.transaction():
            if domain and self.db.execute('SELECT 1 FROM mc_business_operations WHERE legacy_domain=%s AND request_id=%s', (domain, request_id)).fetchone():
                raise BusinessContractError('idempotency_conflict', 'Request ID collides with an existing core operation')
            self.db.execute("INSERT INTO mc_business_operations(scope_sha256,operation,request_id,request_sha256,resource_key,scope,request,state,legacy_domain) VALUES(%s,%s,%s,%s,%s,%s,%s,'claimed',%s)",
                            (digest(scope), operation, request_id, fingerprint, resource, Jsonb(scope), Jsonb(request), domain))
            self._event(scope, operation, request_id, 'claimed', None)
        return self.get(scope, operation, request_id)

    def _event(self, scope, operation, request_id, state, response):
        self.db.execute('INSERT INTO mc_business_operation_events(scope_sha256,operation,request_id,state,response_sha256) VALUES(%s,%s,%s,%s,%s)',
                        (digest(scope), operation, request_id, state, digest(response) if response else None))

    def save(self, row, state, response=None):
        # State updates are projections; the complete transition history is immutable.
        with self.db.transaction():
            self.db.execute('UPDATE mc_business_operations SET state=%s,response=%s,updated_at=now() WHERE scope_sha256=%s AND operation=%s AND request_id=%s',
                            (state, Jsonb(response) if response else None, row['scope_sha256'], row['operation'], row['request_id']))
            self._event(row['scope'], row['operation'], row['request_id'], state, response)
        return self.get(row['scope'], row['operation'], row['request_id'])

    @staticmethod
    def receipt(row):
        return {'operation_name': row['operation'], 'request_id': row['request_id'],
                'request_sha256': row['request_sha256'], 'scope': row['scope'], 'state': row['state'],
                # Hash the receipt-free response to avoid a self-referential digest.
                'result_sha256': digest({**row['response'], 'receipt': None}) if row.get('response') else None}

    def replay(self, row):
        if row.get('response'):
            result = copy.deepcopy(row['response'])
            result['replayed'] = True
            result['receipt'] = self.receipt(row)
            return result
        return None
