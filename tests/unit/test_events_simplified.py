def test_events_under_250_lines():
    with open('models/events.py') as f:
        lines = f.readlines()
    assert len(lines) < 250, f"models/events.py has {len(lines)} lines, expected < 250"


def test_event_service_files_exist():
    import os
    for path in ['services/branch_audit_service.py', 'services/gl_auto_service.py', 'services/events_ai_service.py']:
        assert os.path.exists(path), f"Missing required service file: {path}"


def test_branch_service_has_business_logic():
    from services.branch_audit_service import ensure_branch_liquidity_account, register_branch_event_listeners
    assert callable(ensure_branch_liquidity_account)
    assert callable(register_branch_event_listeners)


def test_gl_service_has_business_logic():
    from services.gl_auto_service import validate_journal_entry_balance, validate_decimal_precision, ensure_balance_consistency
    assert callable(validate_journal_entry_balance)
    assert callable(validate_decimal_precision)
    assert callable(ensure_balance_consistency)


def test_ai_service_has_business_logic():
    from services.events_ai_service import register_ai_event_listeners, register_neural_event_listeners
    assert callable(register_ai_event_listeners)
    assert callable(register_neural_event_listeners)
