"""Celery task for agent query execution per §13.1."""

from __future__ import annotations

from celery import shared_task
from apps.agent.agent import Agent
from apps.queries.models import Query


@shared_task(bind=True)
def run_query_task(self, query_id: str):
    query = Query.objects.get(id=query_id)
    session_ctx = {
        "image_count": query.session.imagery_assets.count(),
        "pair_type": query.image_pair.pair_type if query.image_pair else None,
    }
    return Agent.run(query, session_ctx)
