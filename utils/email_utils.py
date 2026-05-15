import io, base64
from flask_mail import Message
from extensions import mail


# ─────────────────────────────────────────────────────────────
# HELPER — generate QR code as base64 PNG
# ─────────────────────────────────────────────────────────────
def _make_qr_b64(data: str) -> str | None:
    try:
        import qrcode
        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        print(f'QR generation failed: {e}')
        return None


# ─────────────────────────────────────────────────────────────
# HELPER — payment method icon (emoji fallback for plain email)
# ─────────────────────────────────────────────────────────────
def _pm_label(method: str) -> str:
    m = (method or '').upper()
    if m == 'UPI':        return '📱 UPI'
    if m == 'RAZORPAY':   return '⚡ Razorpay'
    if m == 'CARD':       return '💳 Card'
    if m == 'NETBANKING': return '🏦 Net Banking'
    return method or '—'


# ─────────────────────────────────────────────────────────────
# Send owner/admin credentials
# ─────────────────────────────────────────────────────────────
def send_credentials_email(to_email, user_name, user_role, login_email, plain_password):
    subject = f'{user_role.capitalize()} Account Created — CineBook'
    body = f"""Hello {user_name},

Your account has been created in CineBook.

Login Details:
--------------
Role     : {user_role.capitalize()}
Email    : {login_email}
Password : {plain_password}


Please change your password after first login.

Regards,
CineBook Team
"""
    try:
        msg = Message(subject=subject, recipients=[to_email])
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f'Email send failed: {e}')
        return False


# ─────────────────────────────────────────────────────────────
# Booking confirmation — rich HTML + QR code attachment
# ─────────────────────────────────────────────────────────────
def send_booking_confirmation_email(
        to_email, user_name, booking_id,
        movie_title, theater_name, show_date, show_time,
        seat_numbers, total_amount, transaction_ref,
        # optional extras (added for richer email)
        theater_address='', theater_city='', theater_state='',
        payment_method='', screen_name=''):

    subject = f'🎬 Booking Confirmed — {movie_title}'

    # ── QR code data ─────────────────────────────────────────
    qr_lines = [
        'CineBook E-Ticket',
        f'Booking ID : {booking_id}',
        f'Movie      : {movie_title}',
        f'Theater    : {theater_name}',
        f'Date       : {show_date}',
        f'Time       : {show_time}',
        f'Seats      : {seat_numbers}',
        f'Amount     : Rs.{total_amount}',
        f'Method     : {payment_method}',
        f'TXN        : {transaction_ref}',
    ]
    qr_b64 = _make_qr_b64('\n'.join(qr_lines))

    # ── Plain-text fallback ───────────────────────────────────
    address_line = ''
    if theater_address:
        address_line = f'\nAddress         : {theater_address}'
    if theater_city or theater_state:
        address_line += f'\n                  {theater_city}{"," if theater_city and theater_state else ""} {theater_state}'.rstrip()

    plain = f"""Hello {user_name},

Your booking is confirmed! 🎉

Booking Details:
----------------
Booking ID      : {booking_id}
Movie           : {movie_title}
Theater         : {theater_name}{address_line}
Show Date       : {show_date}
Show Time       : {show_time}
Seats           : {seat_numbers}
Total Amount    : ₹{total_amount}
Payment Method  : {_pm_label(payment_method)}
Transaction Ref : {transaction_ref}

Please arrive 15 minutes before the show.
Show your QR code (attached / on ticket page) at the entrance.



Enjoy the movie! 🍿

Regards,
CineBook Team
"""

    # ── HTML email body ───────────────────────────────────────
    venue_detail = theater_name
    if theater_address:
        venue_detail += f'<br><span style="font-size:13px;color:#888">{theater_address}</span>'
    if theater_city or theater_state:
        loc = ', '.join(filter(None, [theater_city, theater_state]))
        venue_detail += f'<br><span style="font-size:13px;color:#888">{loc}</span>'

    qr_html = ''
    if qr_b64:
        qr_html = f'''
        <tr>
          <td colspan="2" style="text-align:center;padding:20px 0 8px">
            <img src="cid:ticket_qr" alt="QR Code"
                 style="width:180px;height:180px;border:6px solid #fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.18)">
            <p style="color:#888;font-size:12px;margin:8px 0 0">
              Scan at theater entrance
            </p>
          </td>
        </tr>'''

    pm_label = _pm_label(payment_method)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0d1117;font-family:'Segoe UI',Arial,sans-serif">
  <div style="max-width:520px;margin:32px auto;background:#161b22;border-radius:16px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.4)">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#e50914,#ff6a00);padding:28px 32px;text-align:center">
      <div style="font-size:28px;margin-bottom:6px">🎬</div>
      <h1 style="margin:0;color:#fff;font-size:22px;font-weight:800;letter-spacing:1px">CineBook</h1>
      <p style="margin:6px 0 0;color:rgba(255,255,255,0.85);font-size:14px">Your ticket is confirmed!</p>
    </div>

    <!-- Success badge -->
    <div style="text-align:center;padding:24px 32px 0">
      <div style="display:inline-block;background:rgba(63,185,80,0.12);border:1.5px solid rgba(63,185,80,0.4);
                  border-radius:24px;padding:8px 22px;color:#3fb950;font-size:14px;font-weight:600">
        ✅ Booking Confirmed
      </div>
      <h2 style="color:#fff;margin:14px 0 4px;font-size:20px">{movie_title}</h2>
      <p style="color:#888;margin:0;font-size:13px">Booking ID: <span style="font-family:monospace;color:#ccc">{booking_id}</span></p>
    </div>

    <!-- Ticket details table -->
    <div style="padding:20px 32px">
      <table style="width:100%;border-collapse:collapse">

        <!-- Theater / venue -->
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px;width:44%;vertical-align:top">
            📍 Venue
          </td>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#e6edf3;font-size:14px;font-weight:600;vertical-align:top">
            {venue_detail}
          </td>
        </tr>

        <!-- Date -->
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px">📅 Show Date</td>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#e6edf3;font-size:14px;font-weight:600">{show_date}</td>
        </tr>

        <!-- Time -->
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px">🕐 Show Time</td>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#ff6a00;font-size:16px;font-weight:700">{show_time}</td>
        </tr>

        <!-- Seats -->
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px">🪑 Seats</td>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#ff6a00;font-size:14px;font-weight:700">{seat_numbers}</td>
        </tr>

        <!-- Amount -->
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px">💰 Amount Paid</td>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#3fb950;font-size:18px;font-weight:800">₹{total_amount}</td>
        </tr>

        <!-- Payment method -->
        <tr>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px">💳 Payment Method</td>
          <td style="padding:10px 0;border-bottom:1px solid #21262d;color:#e6edf3;font-size:14px;font-weight:600">{pm_label}</td>
        </tr>

        <!-- TXN -->
        <tr>
          <td style="padding:10px 0;color:#888;font-size:13px">🔖 Transaction Ref</td>
          <td style="padding:10px 0;color:#888;font-size:12px;font-family:monospace;word-break:break-all">{transaction_ref}</td>
        </tr>

        <!-- QR Code (inline if generated) -->
        {qr_html}

      </table>
    </div>

    

    <!-- Note -->
    <div style="background:#0d1117;padding:16px 32px;text-align:center">
      <p style="color:#888;font-size:12px;margin:0">
        Please arrive <strong style="color:#ccc">15 minutes</strong> before the show.<br>
        Show your QR code at the theater entrance for entry.
      </p>
    </div>

    <!-- Footer -->
    <div style="padding:16px 32px;text-align:center;border-top:1px solid #21262d">
      <p style="color:#555;font-size:11px;margin:0">
        CineBook · Your Movie Booking Platform<br>
        This is an automated email. Please do not reply.
      </p>
    </div>

  </div>
</body>
</html>"""

    # ── Build and send message ────────────────────────────────
    msg = Message(subject=subject, recipients=[to_email])
    msg.body = plain
    msg.html = html

    # Attach QR as inline image
    if qr_b64:
        qr_bytes = base64.b64decode(qr_b64)
        msg.attach(
            filename='ticket_qr.png',
            content_type='image/png',
            data=qr_bytes,
            disposition='inline',
            headers={'Content-ID': '<ticket_qr>'},
        )

    mail.send(msg)


# ─────────────────────────────────────────────────────────────
# Cancellation / refund email
# ─────────────────────────────────────────────────────────────
def send_cancellation_refund_email(to_email, user_name, booking_id, movie_title,
                                   seat_numbers, total_amount, transaction_ref):
    subject = f'Booking Cancelled & Refund Initiated — {movie_title}'
    plain = f"""Hello {user_name},

Your booking has been cancelled successfully.

Cancellation Details:
---------------------
Booking ID      : {booking_id}
Movie           : {movie_title}
Seats           : {seat_numbers}
Refund Amount   : ₹{total_amount}
Transaction Ref : {transaction_ref}

Refund will be credited to your original payment method within 5–7 business days.

We hope to see you again! 🎬

Regards,
CineBook Team
"""
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0d1117;font-family:'Segoe UI',Arial,sans-serif">
  <div style="max-width:480px;margin:32px auto;background:#161b22;border-radius:16px;overflow:hidden">
    <div style="background:linear-gradient(135deg,#21262d,#30363d);padding:24px 32px;text-align:center">
      <div style="font-size:28px;margin-bottom:6px">❌</div>
      <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700">Booking Cancelled</h1>
    </div>
    <div style="padding:24px 32px">
      <p style="color:#e6edf3;margin:0 0 18px">Hello {user_name},</p>
      <p style="color:#888;margin:0 0 20px;font-size:14px">Your booking has been cancelled and a refund has been initiated.</p>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:9px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px">Booking ID</td>
            <td style="padding:9px 0;border-bottom:1px solid #21262d;color:#e6edf3;font-family:monospace;font-size:13px">{booking_id}</td></tr>
        <tr><td style="padding:9px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px">Movie</td>
            <td style="padding:9px 0;border-bottom:1px solid #21262d;color:#e6edf3;font-size:14px;font-weight:600">{movie_title}</td></tr>
        <tr><td style="padding:9px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px">Seats</td>
            <td style="padding:9px 0;border-bottom:1px solid #21262d;color:#e6edf3;font-size:14px">{seat_numbers}</td></tr>
        <tr><td style="padding:9px 0;border-bottom:1px solid #21262d;color:#888;font-size:13px">Refund Amount</td>
            <td style="padding:9px 0;border-bottom:1px solid #21262d;color:#3fb950;font-size:16px;font-weight:700">₹{total_amount}</td></tr>
        <tr><td style="padding:9px 0;color:#888;font-size:13px">TXN Ref</td>
            <td style="padding:9px 0;color:#888;font-size:12px;font-family:monospace">{transaction_ref}</td></tr>
      </table>
      <p style="color:#888;font-size:12px;margin:20px 0 0">
        Refund will be credited within <strong style="color:#ccc">5–7 business days</strong> to your original payment method.
      </p>
    </div>
    <div style="padding:16px 32px;text-align:center;border-top:1px solid #21262d">
      <p style="color:#555;font-size:11px;margin:0">CineBook · Automated notification</p>
    </div>
  </div>
</body>
</html>"""

    msg = Message(subject=subject, recipients=[to_email])
    msg.body = plain
    msg.html = html
    mail.send(msg)


# ─────────────────────────────────────────────────────────────
# Forgot password
# ─────────────────────────────────────────────────────────────
def send_forgot_password_email(to_email, user_name, new_password):
    subject = 'Password Reset — CineBook'
    body = f"""Hello {user_name},

Your password has been reset as requested.

New Temporary Password: {new_password}

Please login and change your password immediately.


If you did not request this, contact support immediately.

Regards,
CineBook Team
"""
    msg = Message(subject=subject, recipients=[to_email])
    msg.body = body
    mail.send(msg)