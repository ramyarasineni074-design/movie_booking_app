from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from extensions import db
from models import ContactMessage, PartnershipRequest
from utils.decorators import handle_exceptions

contact_bp = Blueprint('contact_bp', __name__)


# --------------------------------------------------
# CONTACT PAGE  (complaints / feedback)
# --------------------------------------------------
@contact_bp.route('/contact', methods=['GET', 'POST'])
@handle_exceptions
def contact():
    if request.method == 'POST':
        name         = request.form.get('name', '').strip()
        email        = request.form.get('email', '').strip()
        subject      = request.form.get('subject', '').strip()
        message_type = request.form.get('message_type', 'complaint').strip()
        message      = request.form.get('message', '').strip()

        if not all([name, email, message]):
            flash('Name, email and message are required.', 'danger')
            return redirect(url_for('contact_bp.contact'))

        msg = ContactMessage(
            name=name,
            email=email,
            subject=subject or f'{message_type.title()} from {name}',
            message=message,
            message_type=message_type,
            status='unread',
            created_at=datetime.utcnow()
        )
        db.session.add(msg)
        db.session.commit()

        flash('Your message has been sent! We will get back to you within 24 hours.', 'success')
        return redirect(url_for('contact_bp.contact'))

    return render_template('user/contact.html', active_page='contact')


# --------------------------------------------------
# PARTNER WITH US  (theater owner request)
# --------------------------------------------------
@contact_bp.route('/partner', methods=['GET', 'POST'])
@handle_exceptions
def partner():
    if request.method == 'POST':
        owner_name   = request.form.get('owner_name', '').strip()
        owner_email  = request.form.get('owner_email', '').strip()
        owner_phone  = request.form.get('owner_phone', '').strip()
        brand_name   = request.form.get('brand_name', '').strip()
        city         = request.form.get('city', '').strip()
        state        = request.form.get('state', '').strip()
        num_theaters = request.form.get('num_theaters', '1').strip()
        message      = request.form.get('message', '').strip()

        if not all([owner_name, owner_email, brand_name]):
            flash('Name, email and theater/brand name are required.', 'danger')
            return redirect(url_for('contact_bp.partner'))

        req = PartnershipRequest(
            owner_name=owner_name,
            owner_email=owner_email,
            owner_phone=owner_phone,
            brand_name=brand_name,
            city=city,
            state=state,
            num_theaters=int(num_theaters) if num_theaters.isdigit() else 1,
            message=message,
            status='pending',
            created_at=datetime.utcnow()
        )
        db.session.add(req)
        db.session.commit()

        flash('🎉 Partnership request submitted! Our team will review and contact you within 2-3 business days.', 'success')
        return redirect(url_for('contact_bp.partner'))

    return render_template('user/partner.html', active_page='partner')
