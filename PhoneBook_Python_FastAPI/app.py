# Import the required modules
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import re
import json

with open("config.json", "r") as config_file:
    config_data = json.load(config_file)

phonebook_db = config_data["database"]["pb"]
auditLog_db = config_data["database"]["log"]


# Functions to handle regex validation
def validate_phone_number(phone_number):
    pattern = r'^(?!(\d{6,}))' \
              r'\+?\d{0,3}\s?' \
              r'(\d\s|(\(\d{2}\)\s)|(\(\d{3}\)))?' \
              r'[.-]?\d{2,5}[\s.-]?\d{2,5}[\s.-]?\d{1,9}$'

    match = re.match(pattern, phone_number)
    return bool(match)


def validate_full_name(name):
    pattern = r'^(?=.{1,35}$)(' \
              r'([A-Za-z]+\s?){1,3}' \
              r'|[A-Za-z]+,\s[A-Za-z]+[\sA-Za-z]*' \
              r'|([A-Za-z]+\s)[A-Za-z]\'[A-Za-z]+(\-[A-Za-z]+)?' \
              r'|[A-Za-z]\'[A-Za-z]+\,\s[A-Za-z]+\s[A-Z]\.' \
              r'|[A-Za-z]+\s[A-Za-z]\.\s[A-Za-z]+' \
              r'|[A-Za-z]+\s[A-Za-z]\.\s[A-Z]\'[A-Za-z]+' \
              r'|[A-Za-z]+\,\s[A-Za-z]+\s[A-Z]\.' \
              r')$'

    match = re.match(pattern, name)
    return bool(match)


# Create the FastAPI app
app = FastAPI()

# Create the SQLite database engine
phonebook_engine = create_engine(phonebook_db, echo=True)
auditLog_engine = create_engine(auditLog_db, echo=True)

# Create the base class for the database models
Base = declarative_base()


# Create the PhoneBook model class
class PhoneBook(Base):
    __tablename__ = "phonebook"

    id = Column(Integer, primary_key=True)
    full_name = Column(String)
    phone_number = Column(String)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    action = Column(String)
    full_name = Column(String)
    phone_number = Column(String)


# Create the database schema
Base.metadata.create_all(phonebook_engine)
Base.metadata.create_all(auditLog_engine)

# Create the session class for database operations
phonebook_Session = sessionmaker(bind=phonebook_engine)
auditLog_Session = sessionmaker(bind=auditLog_engine)


# Create the Pydantic model class for request and response data
class Person(BaseModel):
    full_name: str
    phone_number: str


# Define the API endpoints
@app.get("/PhoneBook/list")
def list_phonebook():
    # Get a new session
    session = phonebook_Session()
    # Query all the records in the phonebook table
    phonebook = session.query(PhoneBook).all()

    new_audit_log = AuditLog(action="list")
    session = auditLog_Session()
    session.add(new_audit_log)
    session.commit()

    # Close the session
    session.close()
    # Return the list of records as JSON objects
    return phonebook


@app.post("/PhoneBook/add")
def add_person(person: Person):
    # Get a new session
    session = phonebook_Session()

    # Validating full name and phone number
    if not validate_full_name(person.full_name):
        session.close()
        raise HTTPException(status_code=400, detail="Invalid input. Please check your response and try again.")

    if not validate_phone_number(person.phone_number):
        session.close()
        raise HTTPException(status_code=400, detail="Invalid input. Please check your response and try again.")

    # Check if the person already exists in the database using parameterized queries
    existing_number = session.query(PhoneBook).filter(PhoneBook.phone_number == person.phone_number).first()
    existing_person = session.query(PhoneBook).filter(PhoneBook.full_name == person.full_name).first()

    # If the number exists, raise an exception
    if existing_number:
        session.close()
        raise HTTPException(status_code=400, detail="Phone number already exists in the database")

    # If the person exists, raise an exception
    if existing_person:
        session.close()
        raise HTTPException(status_code=400, detail="Person already exists in the database")

    # Otherwise, create a new PhoneBook record and add it to the database
    new_person = PhoneBook(full_name=person.full_name, phone_number=person.phone_number)
    session.add(new_person)
    session.commit()

    # Close the phonebook database session
    session.close()

    # Perform audit log functionality after all validation and phonebook database actions are completed
    new_audit_log = AuditLog(action="add", full_name=person.full_name, phone_number=person.phone_number)

    # Open a new session for the auit log database
    session = auditLog_Session()
    session.add(new_audit_log)
    session.commit()

    session.close()

    # Return a success message
    return {"message": "Person added successfully"}


@app.put("/PhoneBook/deleteByName")
def delete_by_name(full_name: str):
    # Get a new session
    session = phonebook_Session()
    
    # Validate the full name
    if not validate_full_name(full_name):
        session.close()
        raise HTTPException(status_code=400, detail="Invalid input. Please check your response and try again.")

    # Query the person by name in the database using parameterized query
    person = session.query(PhoneBook).filter(PhoneBook.full_name == full_name).first()

    # If the person does not exist, raise an exception
    if not person:
        session.close()
        raise HTTPException(status_code=404, detail="Person not found in the database")

    # Otherwise, delete the person from the database
    session.delete(person)
    session.commit()

    # Close the session for the phonebook database
    session.close()

    # Perform audit log functionality after all validation and phonebook database actions are completed
    new_audit_log = AuditLog(action="delete-by-name", full_name=person.full_name, phone_number=person.phone_number)

    # Open a new session for the auit log database
    session = auditLog_Session()
    session.add(new_audit_log)
    session.commit()

    session.close()
    # Return a success message
    return {"message": "Person deleted successfully"}


@app.put("/PhoneBook/deleteByNumber")
def delete_by_number(phone_number: str):

    # Get a new session
    session = phonebook_Session()

    # Validate phone number
    if not validate_phone_number(phone_number):
        session.close()
        raise HTTPException(status_code=400, detail="Invalid input. Please check your response and try again.")

    # Query the person by phone number in the database using parameterized query
    person = session.query(PhoneBook).filter(PhoneBook.phone_number == phone_number).first()

    # If the person does not exist, raise an exception
    if not person:
        session.close()
        raise HTTPException(status_code=404, detail="Person not found in the database")

    # Otherwise, delete the person from the database
    session.delete(person)
    session.commit()

    # Close the session for the phonebook database
    session.close()

    # Perform audit log functionality after all validation and phonebook database actions are completed
    new_audit_log = AuditLog(action="delete-by-number", full_name=person.full_name, phone_number=person.phone_number)

    # Open a new session for the auit log database
    session = auditLog_Session()
    session.add(new_audit_log)
    session.commit()

    session.close()

    # Return a success message
    return {"message": "Person deleted successfully"}
