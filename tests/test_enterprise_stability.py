import pytest

from stoa.services import enterprise_stability_service


def test_ops_risk_register_maps_required_services_and_risk_routes():
    register = enterprise_stability_service.ops_risk_register()
    services = {row["service"] for row in register["services"]}
    assert enterprise_stability_service.SERVICE_NAMES.issubset(services)
    for row in register["services"]:
        assert row["owner"]
        assert row["failureMode"]
        assert row["recoveryAction"]
        assert row["sloTarget"]
        assert row["evidenceSource"]
    assert "data_loss" in register["riskCounts"]
    assert "dynamodb" in register["highestRiskRoutes"]["backupRestore"]


def test_backup_restore_drills_cover_core_data_and_lifecycle_boundaries():
    drills = enterprise_stability_service.backup_restore_drills()
    scopes = {item["scope"] for item in drills["drills"]}
    assert "DynamoDB core account/product data" in scopes
    assert "S3/report evidence object metadata" in scopes
    assert drills["productionMutationAllowed"] is False
    assert "legalHold" in drills["dataLifecycle"]
    assert "customerExport" in drills["dataLifecycle"]


def test_incident_runbooks_slo_and_rollback_controls_cover_domains():
    runbooks = enterprise_stability_service.incident_runbooks()
    domains = {item["domain"] for item in runbooks["runbooks"]}
    assert enterprise_stability_service.INCIDENT_DOMAINS.issubset(domains)
    controls = runbooks["rollbackFreezeControls"]
    assert {"backendLambda", "cdk", "frontend", "mobile", "providerFlags", "scheduledJobs"}.issubset(controls)
    dashboard = enterprise_stability_service.slo_dashboard_summary(
        [{"dimension": "availability"}, {"dimension": "provider_blocker"}, {"dimension": "raw_user_id"}]
    )
    assert dashboard["eventCounts"]["availability"] == 1
    assert dashboard["eventCounts"]["provider_blocker"] == 1
    assert dashboard["eventCounts"]["unknown"] == 1


def test_access_rotation_and_compliance_evidence_is_metadata_only():
    evidence = enterprise_stability_service.access_rotation_evidence(dry_run=True)
    surfaces = {item["surface"] for item in evidence["inventory"]}
    assert {"admin_access", "cognito_groups", "aws_profiles", "provider_credentials", "ci_deploy_credentials", "break_glass_access"}.issubset(surfaces)
    assert evidence["rotationEvidence"]["state"] == "dry_run_recorded"
    assert evidence["privacy"]["metadataOnly"] is True


def test_release_gate_evidence_records_blockers_and_v5_24_recommendation():
    evidence = enterprise_stability_service.release_gate_evidence()
    assert evidence["releaseState"] == "enterprise-hardening-ready-local-contracts"
    assert evidence["incidentSloRollback"]["incidentDomainCount"] >= 9
    assert evidence["blockers"]
    assert "limited production pilot" in evidence["v5_24Recommendation"]


def test_enterprise_evidence_rejects_private_fields():
    with pytest.raises(ValueError):
        enterprise_stability_service.assert_metadata_safe({"secret": "not allowed"})
    with pytest.raises(ValueError):
        enterprise_stability_service.assert_metadata_safe({"nested": {"provider_payload": {"x": 1}}})
