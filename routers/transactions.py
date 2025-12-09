from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from database import get_db
from models.transaction import Transaction
from models.user import User
from utils.auth_dependency import get_current_user

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])

class TransactionResponse(BaseModel):
    id: int
    customer_id: int
    order_id: Optional[int]
    amount: float
    paid: float
    due: float
    date: datetime
    is_payment: bool
    
    class Config:
        from_attributes = True

class PaymentCreate(BaseModel):
    customer_id: int
    amount: float

class AccountStatement(BaseModel):
    customer_id: int
    total_orders: int
    total_amount: float
    total_paid: float
    total_due: float
    transactions: List[TransactionResponse]

@router.get("/", response_model=List[TransactionResponse])
def get_transactions(customer_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Transaction)
    if customer_id:
        query = query.filter(Transaction.customer_id == customer_id)
    transactions = query.order_by(Transaction.date.desc()).all()
    return transactions

@router.post("/payment", response_model=TransactionResponse)
def record_payment(request: PaymentCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Get customer's total due
    total_due = db.query(func.sum(Transaction.due)).filter(
        Transaction.customer_id == request.customer_id
    ).scalar() or 0.0
    
    if request.amount > total_due:
        raise HTTPException(status_code=400, detail="Payment amount exceeds total due")
    
    # Create payment transaction
    transaction = Transaction(
        customer_id=request.customer_id,
        amount=request.amount,
        paid=request.amount,
        due=-request.amount,
        is_payment=True
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    
    return transaction

@router.get("/statement/{customer_id}", response_model=AccountStatement)
def get_account_statement(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    transactions = db.query(Transaction).filter(
        Transaction.customer_id == customer_id
    ).order_by(Transaction.date.desc()).all()
    
    total_amount = db.query(func.sum(Transaction.amount)).filter(
        Transaction.customer_id == customer_id,
        Transaction.is_payment == False
    ).scalar() or 0.0
    
    total_paid = db.query(func.sum(Transaction.paid)).filter(
        Transaction.customer_id == customer_id
    ).scalar() or 0.0
    
    total_due = db.query(func.sum(Transaction.due)).filter(
        Transaction.customer_id == customer_id
    ).scalar() or 0.0
    
    total_orders = db.query(func.count(Transaction.id)).filter(
        Transaction.customer_id == customer_id,
        Transaction.is_payment == False
    ).scalar() or 0
    
    return AccountStatement(
        customer_id=customer_id,
        total_orders=total_orders,
        total_amount=float(total_amount),
        total_paid=float(total_paid),
        total_due=float(total_due),
        transactions=transactions
    )
