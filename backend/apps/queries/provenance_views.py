from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.queries.models import Query
from apps.queries.provenance import verify_provenance_ledger


class QueryProvenanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id, query_id):
        query = get_object_or_404(Query.objects.select_related("session", "user"), id=query_id, session_id=session_id)
        if query.user_id != request.user.id:
            return Response({"detail": "Not found."}, status=404)
        verification = verify_provenance_ledger(query)
        records = [
            {
                "sequence": row.sequence,
                "event_type": row.event_type,
                "execution_step_id": str(row.execution_step_id) if row.execution_step_id else None,
                "payload": row.payload,
                "previous_hash": row.previous_hash or None,
                "record_hash": row.record_hash,
                "created_at": row.created_at.isoformat(),
            }
            for row in query.provenance_records.order_by("sequence")
        ]
        return Response({"query_id": str(query.id), "verification": verification, "records": records})
