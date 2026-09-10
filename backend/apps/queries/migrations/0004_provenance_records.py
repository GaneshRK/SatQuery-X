from django.db import migrations, models
import uuid
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("queries", "0003_executionstep_agent_type_executionstep_evidence_refs_and_more")]
    operations = [
        migrations.CreateModel(
            name="ProvenanceRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("sequence", models.PositiveIntegerField()),
                ("event_type", models.CharField(max_length=64)),
                ("payload", models.JSONField(default=dict)),
                ("previous_hash", models.CharField(blank=True, default="", max_length=64)),
                ("record_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField()),
                ("execution_step", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="provenance_records", to="queries.executionstep")),
                ("query", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="provenance_records", to="queries.query")),
            ],
            options={
                "ordering": ["sequence"],
            },
        ),
        migrations.AddConstraint(
            model_name="provenancerecord",
            constraint=models.UniqueConstraint(fields=("query", "sequence"), name="unique_query_provenance_sequence"),
        ),
        migrations.AddIndex(
            model_name="provenancerecord",
            index=models.Index(fields=["query", "sequence"], name="prov_query_sequence_idx"),
        ),
        migrations.AddIndex(
            model_name="provenancerecord",
            index=models.Index(fields=["query", "event_type"], name="prov_query_event_idx"),
        ),
    ]
