#!/usr/bin/env python
"""
Standalone test of Phoenix API components without Docker.
Proves evidence extraction, classification, and orchestrator structure.
"""
import sys
import os

# Add repo root to path
repo_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, repo_root)

# Change to repo root for relative imports
os.chdir(repo_root)

def test_evidence_extraction():
    """Test that evidence.py uses existing EvidenceInput and adapts payloads."""
    print("\n" + "="*70)
    print("TEST 1: Evidence Extraction (thin adapter to existing LLM engine)")
    print("="*70)
    
    from phoenix_api.app.evidence import (
        extract_evidence_from_ci_payload,
        extract_evidence_from_docker_incident,
    )
    from agent.ai.llm_engine.diagnosis import EvidenceInput
    
    # Test CI payload
    ci_payload = {
        'source': 'github_ci',
        'repository': 'owner/repo',
        'commit': 'abc1234567890def1234567890def12345678901',
        'branch': 'main',
        'run_id': '12345',
        'run_url': 'https://github.com/owner/repo/actions/runs/12345',
        'workflow': 'tests',
        'stage': 'test',
        'logs': '''
test_app.py::test_get_user FAILED

test_app.py:10: in test_get_user
    assert get_user(user) == 'Alice'
app.py:3: in get_user
    return user['name']
E   KeyError: 'name'
        '''
    }
    
    evidence = extract_evidence_from_ci_payload(ci_payload)
    assert isinstance(evidence, EvidenceInput), f"Expected EvidenceInput, got {type(evidence)}"
    assert evidence.error_type == 'KeyError', f"Expected KeyError, got {evidence.error_type}"
    print("✓ CI payload → EvidenceInput (KeyError detected)")
    print(f"  error_message: {evidence.error_message}")
    print(f"  extra_context: {evidence.extra_context}")
    
    # Test Docker payload
    docker_payload = {
        'source': 'docker_runtime',
        'repository': 'owner/repo',
        'commit': 'abc1234567890def1234567890def12345678901',
        'branch': 'main',
        'container_name': 'user-service-1',
        'error_type': 'TypeError',
        'error_message': "'NoneType' object is not subscriptable",
        'logs': 'Traceback...',
        'stack_trace': 'Traceback (most recent call last):\n  File "app.py", line 42, in get_user\n    return user[\'name\']\nTypeError: \'NoneType\' object is not subscriptable'
    }
    
    evidence2 = extract_evidence_from_docker_incident(docker_payload)
    assert isinstance(evidence2, EvidenceInput), f"Expected EvidenceInput, got {type(evidence2)}"
    assert evidence2.error_type == 'TypeError', f"Expected TypeError, got {evidence2.error_type}"
    print("✓ Docker payload → EvidenceInput (TypeError detected)")
    print(f"  error_message: {evidence2.error_message}")
    print(f"  extra_context: {evidence2.extra_context}")
    
    print("\n✅ Evidence extraction is a thin adapter. Does NOT duplicate existing LLM engine.")


def test_failure_classification():
    """Test that classification correctly identifies code vs non-code."""
    print("\n" + "="*70)
    print("TEST 2: Failure Classification")
    print("="*70)
    
    from phoenix_api.app.classifier import FailureClassifier
    
    # Code-level errors
    classification, reason = FailureClassifier.classify(
        error_type="TypeError",
        error_message="'NoneType' object is not subscriptable",
        logs=""
    )
    assert classification == "code", f"Expected code, got {classification}"
    print(f"✓ TypeError → code: {reason}")
    
    # Non-code errors
    classification, reason = FailureClassifier.classify(
        error_type="NetworkError",
        error_message="connection refused",
        logs="Failed to connect to redis"
    )
    assert classification == "non_code", f"Expected non_code, got {classification}"
    print(f"✓ Network error → non_code: {reason}")
    
    # Unknown defaults to code (conservative)
    classification, reason = FailureClassifier.classify(
        error_type="CustomError",
        error_message="something went wrong",
        logs=""
    )
    assert classification == "code", f"Expected code (default), got {classification}"
    print(f"✓ Unknown error → code (conservative): {reason}")
    
    print("\n✅ Failure classification works correctly.")


def test_incident_store_structure():
    """Test that incident store methods exist and have correct signatures."""
    print("\n" + "="*70)
    print("TEST 3: Incident Store Structure (methods exist)")
    print("="*70)
    
    from phoenix_api.app.incident_store import IncidentStore
    import inspect
    
    methods = [
        'generate_incident_id',
        'check_duplicate',
        'create_incident',
        'get_incident',
        'list_incidents',
        'update_incident_status',
        'set_validation_result',
        'set_git_info',
        'set_error',
    ]
    
    for method_name in methods:
        assert hasattr(IncidentStore, method_name), f"Missing method: {method_name}"
        method = getattr(IncidentStore, method_name)
        assert callable(method), f"{method_name} is not callable"
        print(f"✓ {method_name}")
    
    print("\n✅ Incident store has all required methods.")


def test_orchestrator_structure():
    """Test that orchestrator imports correctly and has main entry point."""
    print("\n" + "="*70)
    print("TEST 4: Orchestrator Structure")
    print("="*70)
    
    from phoenix_api.app.orchestrator import PhoenixOrchestrator
    import inspect
    
    orchestrator = PhoenixOrchestrator()
    assert hasattr(orchestrator, 'process_incident'), "Missing process_incident method"
    assert callable(orchestrator.process_incident), "process_incident is not callable"
    print("✓ PhoenixOrchestrator.process_incident() exists")
    
    # Check that it has lazy initialization for LLM and Sandbox
    assert hasattr(orchestrator, '_get_llm_engine'), "Missing _get_llm_engine"
    assert hasattr(orchestrator, '_get_sandbox_pipeline'), "Missing _get_sandbox_pipeline"
    print("✓ Lazy loading of LLM and Sandbox (avoids hard dependency at import)")
    
    print("\n✅ Orchestrator structure is correct.")


def test_config_loading():
    """Test that config loads environment variables correctly."""
    print("\n" + "="*70)
    print("TEST 5: Configuration")
    print("="*70)
    
    # Set required env var for test
    os.environ['PHOENIX_WEBHOOK_SECRET'] = 'test-secret'
    
    try:
        # Need to reload the module since it already loaded
        import importlib
        import phoenix_api.app.config as config_module
        importlib.reload(config_module)
        
        from phoenix_api.app.config import config
        assert config.PHOENIX_WEBHOOK_SECRET == 'test-secret', "Webhook secret not loaded"
        assert config.MONGO_URI == "mongodb://localhost:27017", "Default MONGO_URI not set"
        assert config.MONGO_DB_NAME == "phoenix", "Default DB name not set"
        print("✓ Config loads from environment variables")
        print(f"  MONGO_URI: {config.MONGO_URI}")
        print(f"  MONGO_DB_NAME: {config.MONGO_DB_NAME}")
        print(f"  PHOENIX_WEBHOOK_SECRET: {config.PHOENIX_WEBHOOK_SECRET}")
        print(f"  PHOENIX_REPO_PATH: {config.PHOENIX_REPO_PATH}")
        print(f"  GITHUB_REPO: {config.GITHUB_REPO}")
        
    finally:
        # Clean up
        del os.environ['PHOENIX_WEBHOOK_SECRET']
    
    print("\n✅ Configuration system works correctly.")


def test_no_duplication():
    """Verify evidence.py is NOT duplicating the existing LLM engine."""
    print("\n" + "="*70)
    print("TEST 6: No Duplication of Existing Modules")
    print("="*70)
    
    # Check that we're using existing EvidenceInput
    from phoenix_api.app.evidence import extract_evidence_from_ci_payload
    from agent.ai.llm_engine.diagnosis import EvidenceInput
    
    payload = {
        'source': 'github_ci',
        'repository': 'test/repo',
        'commit': 'abc123',
        'branch': 'main',
        'run_id': '1',
        'logs': 'KeyError: foo'
    }
    
    result = extract_evidence_from_ci_payload(payload)
    # The result should be directly from agent.ai.llm_engine
    assert type(result).__module__.startswith('agent.ai.llm_engine'), \
        f"EvidenceInput not from correct module: {type(result).__module__}"
    print(f"✓ Evidence extraction returns EvidenceInput from {type(result).__module__}")
    
    # Verify we're not duplicating diagnosis, patch, or sandbox
    import phoenix_api.app.evidence as evidence_module
    source = inspect.getsource(evidence_module)
    assert 'class EvidenceInput' not in source, "evidence.py duplicates EvidenceInput!"
    assert 'class DiagnosisResult' not in source, "evidence.py duplicates DiagnosisResult!"
    assert 'class PatchResult' not in source, "evidence.py duplicates PatchResult!"
    print("✓ No class duplication in evidence.py")
    
    print("\n✅ No duplication of existing modules.")


def test_schema_validation():
    """Test that API schemas are correctly defined."""
    print("\n" + "="*70)
    print("TEST 7: API Schema Validation")
    print("="*70)
    
    from phoenix_api.app.schemas import (
        CIWebhookPayload,
        DockerIncidentPayload,
        IncidentResponse,
        IncidentsListResponse,
    )
    
    # Test CI payload parsing
    ci_data = {
        'source': 'github_ci',
        'repository': 'owner/repo',
        'commit': 'abc123',
        'branch': 'main',
        'run_id': '123',
        'run_url': 'https://...',
        'workflow': 'test',
    }
    ci = CIWebhookPayload(**ci_data)
    assert ci.source == 'github_ci'
    print("✓ CIWebhookPayload schema validates CI payload")
    
    # Test Docker payload parsing
    docker_data = {
        'source': 'docker_runtime',
        'repository': 'owner/repo',
        'commit': 'abc123',
        'branch': 'main',
        'container_name': 'app-1',
        'error_type': 'TypeError',
        'error_message': 'test',
    }
    docker = DockerIncidentPayload(**docker_data)
    assert docker.source == 'docker_runtime'
    print("✓ DockerIncidentPayload schema validates Docker payload")
    
    # Test response schemas
    response = IncidentResponse(incident_id='INC-001', status='detected')
    assert response.incident_id == 'INC-001'
    print("✓ IncidentResponse schema defined")
    
    print("\n✅ API schema validation works correctly.")


def main():
    """Run all tests."""
    print("\n" + "🔥 PHOENIX API COMPONENT TESTS 🔥".center(70))
    print("(No Docker or Database required)")
    
    try:
        test_no_duplication()
        test_evidence_extraction()
        test_failure_classification()
        test_incident_store_structure()
        test_orchestrator_structure()
        test_config_loading()
        test_schema_validation()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED".center(70))
        print("="*70)
        print("\nSummary:")
        print("  ✓ Evidence extraction is a thin adapter (uses existing LLMEngine)")
        print("  ✓ Failure classification correctly separates code vs infrastructure")
        print("  ✓ Incident store has all CRUD + atomic ID generation methods")
        print("  ✓ Orchestrator structure is correct with lazy LLM/Sandbox init")
        print("  ✓ Configuration system loads from environment")
        print("  ✓ No duplication of existing modules (LLM, Sandbox, Diagnosis)")
        print("  ✓ API schemas correctly validate CI and Docker payloads")
        print("="*70)
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
