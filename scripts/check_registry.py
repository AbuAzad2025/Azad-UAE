from extensions import db
from flask import Flask
from tests.conftest import TestConfig

app = Flask(__name__)
app.config.from_object(TestConfig)
db.init_app(app)

with app.app_context():
    from sqlalchemy.orm import Session
    print("type(db.session):", type(db.session))
    print("type(db.session.registry):", type(db.session.registry))
    print("callable(db.session.registry):", callable(db.session.registry))
    
    # Check if registry() works
    try:
        r = db.session.registry()
        print(f"registry() returns: {type(r)}")
    except Exception as e:
        print(f"registry() error: {e}")
    
    # Check if registry.set exists
    try:
        print(f"has set: {hasattr(db.session.registry, 'set')}")
        print(f"has clear: {hasattr(db.session.registry, 'clear')}")
    except Exception as e:
        print(f"registry attr error: {e}")
    
    # Try using registry.set
    sess = Session()
    try:
        db.session.registry.set(sess)
        print("registry.set(sess) worked!")
    except Exception as e:
        try:
            db.session.registry().set(sess)
            print("registry().set(sess) worked!")
        except Exception as e2:
            print(f"registry().set error: {e2}")
    
    db.session.remove()
