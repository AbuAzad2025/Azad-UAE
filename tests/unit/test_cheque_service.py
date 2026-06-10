def test_service_exists():
    from services.cheque_service import (
        validate_cheque,
        calculate_amount_aed,
        process_cheque_receive,
        process_cheque_issue,
        process_cheque_deposit,
        process_cheque_clear,
        process_cheque_bounce,
        process_cheque_cancel,
    )
    assert validate_cheque is not None
    assert calculate_amount_aed is not None
    assert process_cheque_receive is not None
    assert process_cheque_issue is not None
    assert process_cheque_deposit is not None
    assert process_cheque_clear is not None
    assert process_cheque_bounce is not None
    assert process_cheque_cancel is not None


def test_model_imports():
    from models.cheque import Cheque
    from services.cheque_service import validate_cheque
    assert Cheque is not None
    assert validate_cheque is not None
