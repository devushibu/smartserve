from flask import Flask, render_template, request, redirect, session, jsonify
from database import users, providers, bookings, payments, time_slots
from bson.objectid import ObjectId
import os
from werkzeug.utils import secure_filename

# Compute paths relative to this file's location (backend/)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, '..', 'frontend', 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.secret_key = "smartserve"

# ---------------- UPLOAD CONFIGURATION ----------------
UPLOAD_FOLDER = os.path.join(STATIC_DIR, 'uploads', 'certificates')
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------- ADMIN LOGIN DETAILS ----------------
ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "admin123"

# ---------------- HOME PAGE ----------------
@app.route('/')
def index():
    return render_template("auth/index.html")


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET','POST'])
def login():

    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']

        # 1. ADMIN LOGIN
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['admin'] = email
            return redirect('/admin')

        # 2. USER LOGIN
        user = users.find_one({
            "email": email,
            "password": password
        })
        if user:
            session['user'] = email
            return redirect('/user_home')

        # 3. PROVIDER LOGIN (ONLY IF VERIFIED)
        provider = providers.find_one({
            "email": email,
            "password": password
        })
        if provider:
            if provider.get("verified"):
                session['provider'] = email
                return redirect('/provider_home')
            else:
                return render_template("auth/login.html", error="Provider account not verified yet.")

        # NO MATCH
        return render_template("auth/login.html", error="Invalid credentials. Please try again.")

    return render_template("auth/login.html")


# ---------------- USER REGISTER ----------------
@app.route('/register_user', methods=['GET','POST'])
def register_user():

    if request.method == "POST":

        data = dict(request.form)

        users.insert_one(data)

        return redirect('/login')

    return render_template("auth/register_user.html")


# ---------------- PROVIDER REGISTER ----------------
@app.route('/register_provider', methods=['GET','POST'])
def register_provider():

    if request.method == "POST":

        data = dict(request.form)
        data["verified"] = False   # IMPORTANT
        
        # Handle file upload
        if 'certificate' not in request.files:
            return "No certificate file uploaded", 400
            
        file = request.files['certificate']
        if file.filename == '':
            return "No selected file", 400
            
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Create a unique filename to prevent overwrites
            unique_filename = f"{data['email']}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            # Store the relative path in the database (using forward slashes for web)
            data["certificate"] = f"uploads/certificates/{unique_filename}"
        else:
            return "Invalid file type. Only PDF, PNG, JPG, JPEG are allowed.", 400

        providers.insert_one(data)

        return redirect('/login')

    return render_template("auth/register_provider.html")


# ---------------- ADMIN PANEL ----------------
@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect('/login')

    return render_template("admin/admin_home.html")

# ---------------- ADMIN SUB-PAGES ----------------
@app.route('/admin_verify')
def admin_verify():
    if not session.get('admin'):
        return redirect('/login')
    all_providers = providers.find()
    return render_template("admin/admin_verify.html", providers=all_providers)

@app.route('/admin_users')
def admin_users():
    if not session.get('admin'):
        return redirect('/login')
    all_users = users.find()
    return render_template("admin/admin_users.html", users=all_users)

@app.route('/admin_providers')
def admin_providers():
    if not session.get('admin'):
        return redirect('/login')
    verified_providers = list(providers.find({"verified": True}))
    return render_template("admin/admin_providers.html", providers=verified_providers)

@app.route('/admin_bookings')
def admin_bookings():
    if not session.get('admin'):
        return redirect('/login')
    all_bookings = list(bookings.find())
    for b in all_bookings:
        provider = providers.find_one({"email": b.get("provider")})
        b["service"] = provider.get("service", "Unknown") if provider else "Unknown"

    return render_template("admin/admin_bookings.html", bookings=all_bookings)

@app.route('/admin_payments')
def admin_payments():
    if not session.get('admin'):
        return redirect('/login')
    
    all_payments = list(payments.find())
    for p in all_payments:
        # Cross-reference booking to get provider info
        booking = bookings.find_one({"_id": p.get("booking_id")})
        p["provider"] = booking.get("provider", "Unknown") if booking else "Unknown"
        
        # Cross-reference provider to get service type
        provider = providers.find_one({"email": p["provider"]})
        p["service"] = provider.get("service", "Unknown") if provider else "Unknown"

    return render_template("admin/admin_payments.html", payments=all_payments)
    

# ---------------- REMOVE PROVIDER ----------------
@app.route('/admin_remove_provider/<email>', methods=['POST'])
def admin_remove_provider(email):
    if not session.get('admin'):
        return redirect('/login')

    providers.delete_one({"email": email})
    return redirect('/admin_providers')


# ---------------- VERIFY PROVIDER ----------------
@app.route('/verify/<email>')
def verify(email):

    providers.update_one(
        {"email": email},
        {"$set": {"verified": True}}
    )

    return redirect('/admin_verify')


# ---------------- USER HOME ----------------
@app.route('/user_home')
def user_home():

    user_email = session.get('user')
    mybookings = bookings.find({"user": user_email}) if user_email else []

    service_filter = request.args.get('service', '')
    location_filter = request.args.get('location', '')

    query = {"verified": True}
    if service_filter:
        query["service"] = {"$regex": service_filter, "$options": "i"}
    if location_filter:
        query["location"] = {"$regex": location_filter, "$options": "i"}

    plist = list(providers.find(query))

    return render_template("user/user_home.html",
                           providers=plist,
                           service=service_filter,
                           location=location_filter)

# ---------------- MY BOOKINGS ----------------
@app.route('/my_bookings')
def my_bookings():
    user_email = session.get('user')
    if not user_email:
        return redirect('/login')

    mybookings = list(bookings.find({"user": user_email}))
    
    # Append the service name for each booking by querying the provider
    for b in mybookings:
        provider = providers.find_one({"email": b.get("provider")})
        b["service"] = provider.get("service", "Unknown") if provider else "Unknown"
        
    return render_template("user/my_bookings.html", bookings=mybookings)

# ---------------- PROVIDER PROFILE ----------------
@app.route('/provider_profile/<email>')
def provider_profile(email):
    
    provider = providers.find_one({"email": email})
    
    return render_template("user/provider_profile.html", provider=provider)


# ---------------- BOOK SERVICE ----------------
@app.route('/book/<email>')
def book(email):

    provider = providers.find_one({"email": email})

    return render_template("user/booking.html",
                           provider=provider)


# ---------------- PAYMENT ----------------
@app.route('/payment', methods=['POST'])
def payment():

    booking = dict(request.form)
    
    user_email = session.get('user', 'Guest')
    booking["user"] = user_email
    booking["status"] = "confirmed"
    
    # Capture payment mode
    payment_mode = booking.get("payment_mode", "Cash")
    
    # Determine payment status
    pay_status = "Paid" if payment_mode != "Cash" else "Unpaid"
    
    booking["payment"] = pay_status

    # Store the booking and get its ID
    inserted_booking = bookings.insert_one(booking)
    booking_id = inserted_booking.inserted_id

    # Store the payment
    payments.insert_one({
        "user": user_email,
        "booking_id": booking_id,
        "amount": booking.get("amount", "500"),
        "payment_mode": payment_mode,
        "status": pay_status
    })

    return render_template("user/payment_success.html")


# ---------------- API: GET AVAILABLE SLOTS ----------------
@app.route('/api/slots/<email>')
def get_slots(email):
    date = request.args.get('date')
    
    # Initialize default slots if collection is empty
    if time_slots.count_documents({}) == 0:
        default_slots = [
            {"slot": "9:00-10:00"},
            {"slot": "10:00-11:00"},
            {"slot": "11:00-12:00"},
            {"slot": "13:00-14:00"},
            {"slot": "14:00-15:00"}
        ]
        time_slots.insert_many(default_slots)

    # Fetch slots from DB
    all_slots = list(time_slots.find({}, {"_id": 0, "slot": 1}))
    TIME_SLOTS = [s["slot"] for s in all_slots]

    if not date:
        return jsonify([])
    
    booked = list(bookings.find({"provider": email, "date": date}))
    booked_slots = [b.get("slot") for b in booked]
    available_slots = [slot for slot in TIME_SLOTS if slot not in booked_slots]
    return jsonify(available_slots)


# ---------------- PROVIDER DASHBOARD ----------------
@app.route('/provider_home')
def provider_home():
    provider_email = session.get('provider')
    if not provider_email:
        return redirect('/login')

    return render_template("provider/provider_home.html")

# ---------------- ASSIGNED WORKS ----------------
@app.route('/provider_assigned')
def provider_assigned():
    provider_email = session.get('provider')
    if not provider_email:
        return redirect('/login')

    # Fetch all bookings that are NOT completed
    mybookings = list(bookings.find({"provider": provider_email, "status": {"$ne": "Completed"}}))
    for b in mybookings:
        user = users.find_one({"email": b.get("user")})
        if user:
            b["user_name"] = user.get("name", "Unknown")
            b["user_phone"] = user.get("phone", "N/A")
        else:
            b["user_name"] = "Unknown"
            b["user_phone"] = "N/A"

    return render_template("provider/provider_assigned.html", bookings=mybookings)

# ---------------- COMPLETED WORKS ----------------
@app.route('/provider_completed')
def provider_completed():
    provider_email = session.get('provider')
    if not provider_email:
        return redirect('/login')

    # Fetch ONLY completed bookings
    mybookings = list(bookings.find({"provider": provider_email, "status": "Completed"}))
    for b in mybookings:
        user = users.find_one({"email": b.get("user")})
        if user:
            b["user_name"] = user.get("name", "Unknown")
            b["user_phone"] = user.get("phone", "N/A")
        else:
            b["user_name"] = "Unknown"
            b["user_phone"] = "N/A"

    return render_template("provider/provider_completed.html", bookings=mybookings)


# ---------------- UPDATE BOOKING STATUS ----------------
@app.route('/update_booking/<id>', methods=['POST'])
def update_booking(id):
    if not session.get('provider'):
        return redirect('/login')

    new_status = request.form.get('status')
    redirect_target = request.args.get('redirect', 'home')

    # Guard: Check current status before updating
    current_booking = bookings.find_one({"_id": ObjectId(id)})
    if not current_booking or "Cancelled" in current_booking.get("status", ""):
        return redirect('/provider_assigned' if redirect_target == 'assigned' else '/provider_home')

    if new_status:
        # If provider selects cancelled, make it specific
        if new_status.lower() == 'cancelled':
            new_status = "Cancelled by Provider"
            
        bookings.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"status": new_status}}
        )

    if redirect_target == 'assigned':
        return redirect('/provider_assigned')
    return redirect('/provider_home')


# ---------------- CANCEL BOOKING ----------------
@app.route('/cancel/<id>', methods=['GET', 'POST'])
def cancel(id):
    # Guard: Check current status
    current_booking = bookings.find_one({"_id": ObjectId(id)})
    if current_booking and current_booking.get("status") != "Completed":
        bookings.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"status": "Cancelled by User"}}
        )

    return redirect('/my_bookings')


# ---------------- UPDATE PAYMENT STATUS ----------------
@app.route('/update_payment/<id>', methods=['POST'])
def update_payment(id):
    if not session.get('provider'):
        return redirect('/login')

    # Guard: Don't mark cancelled bookings as paid by route direct access
    current_booking = bookings.find_one({"_id": ObjectId(id)})
    if not current_booking or "Cancelled" in current_booking.get("status", ""):
        return redirect('/provider_home')

    # Update payment status in both collections
    bookings.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"payment": "Paid"}}
    )
    payments.update_one(
        {"booking_id": ObjectId(id)},
        {"$set": {"status": "Paid"}}
    )

    # Determine redirect based on previous page or default to home
    redirect_target = request.args.get('redirect', 'home')
    if redirect_target == 'assigned':
        return redirect('/provider_assigned')
    elif redirect_target == 'completed':
        return redirect('/provider_completed')
    return redirect('/provider_home')


# ---------------- RUN APP ----------------
if __name__ == '__main__':
    app.run(debug=True)