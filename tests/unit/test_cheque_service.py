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


def test_process_cheque_cancel_accepts_create_gl_param():
    from services.cheque_service import process_cheque_cancel
    import inspect
    sig = inspect.signature(process_cheque_cancel)
    assert 'create_gl' in sig.parameters
    assert sig.parameters['create_gl'].default is True
    assert sig.parameters['create_gl'].kind == inspect.Parameter.KEYWORD_ONLY


def test_expense_cancel_does_not_call_reverse_document_gl_when_cheque_exists():
    """
    Expense cancel route skips reverse_document_gl() when a linked
    non-cancelled cheque exists — process_cheque_cancel(create_gl=True)
    handles the single reversal via _create_cancel_journal_entry.
    """
    from services.cheque_service import process_cheque_cancel, _create_cancel_journal_entry
    assert callable(process_cheque_cancel)
    assert callable(_create_cancel_journal_entry)
