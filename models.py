from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # hashed password
    role = db.Column(db.String(20), nullable=False)  # "doctor" or "other"

    # relationship: a doctor can have many medbox codes
    medbox_codes = db.relationship("MedBoxCode", back_populates="creator", lazy=True)


class MedBoxCode(db.Model):
    __tablename__ = "med_box_codes"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True, default="MedBox")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # relationship to creator and to medicines through medbox
    creator = db.relationship("User", back_populates="medbox_codes")
    medbox = db.relationship("MedBox", back_populates="code_obj", uselist=False)


class MedBox(db.Model):
    __tablename__ = "med_boxes"
    id = db.Column(db.Integer, primary_key=True)

    # link to code record
    code_id = db.Column(db.Integer, db.ForeignKey("med_box_codes.id"), nullable=False)
    code_obj = db.relationship("MedBoxCode", back_populates="medbox")

    # a medbox has many medicines
    medicines = db.relationship("Medicine", back_populates="medbox", lazy=True, cascade="all, delete-orphan")


class Medicine(db.Model):
    __tablename__ = "medicines"
    id = db.Column(db.Integer, primary_key=True)
    medbox_id = db.Column(db.Integer, db.ForeignKey("med_boxes.id"), nullable=False)
    medbox = db.relationship("MedBox", back_populates="medicines")

    name = db.Column(db.String(150), nullable=False)
    # store time as HH:MM string (makes API/device parsing simple)
    time = db.Column(db.String(5), nullable=False)
