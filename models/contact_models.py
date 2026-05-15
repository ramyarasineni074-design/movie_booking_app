from extensions import db
from datetime import datetime

class ContactMessage(db.Model):
    __tablename__ = 'contact_messages'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    name = db.Column(db.String(200), nullable=False, index=True)
    email = db.Column(db.String(300), nullable=False, index=True)

    subject = db.Column(db.String(300))
    message = db.Column(db.Text, nullable=False)

    message_type = db.Column(db.String(50), default='complaint', index=True)
    status = db.Column(db.String(50), default='unread', index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.Index('idx_status_type', 'status', 'message_type'),
        db.Index('idx_email_created', 'email', 'created_at'),
    )


    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "subject": self.subject,
            "message": self.message,
            "message_type": self.message_type,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<ContactMessage {self.id} from {self.email}>"
    

from extensions import db
from datetime import datetime

class PartnershipRequest(db.Model):
    __tablename__ = 'partnership_requests'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    owner_name = db.Column(db.String(200), nullable=False, index=True)
    owner_email = db.Column(db.String(300), nullable=False, index=True)
    owner_phone = db.Column(db.String(20), index=True)

    brand_name = db.Column(db.String(250), nullable=False, index=True)

    city = db.Column(db.String(250), index=True)
    state = db.Column(db.String(200), index=True)

    num_theaters = db.Column(db.Integer, default=1)

    message = db.Column(db.Text)

    status = db.Column(db.String(50), default='pending', index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.Index('idx_status_created', 'status', 'created_at'),
        db.UniqueConstraint('owner_email', 'brand_name', name='uq_owner_brand'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "owner_phone": self.owner_phone,
            "brand_name": self.brand_name,
            "city": self.city,
            "state": self.state,
            "num_theaters": self.num_theaters,
            "message": self.message,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<PartnershipRequest {self.brand_name} by {self.owner_email}>"