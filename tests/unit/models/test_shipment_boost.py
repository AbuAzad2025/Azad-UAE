from models.shipment import Shipment

def test_shipment_import_and_class():
    assert Shipment is not None
    assert hasattr(Shipment, '__table__')
