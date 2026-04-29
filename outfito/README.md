# OUTFITO – Premium E-commerce Platform

## 📖 Project Description

OUTFITO is a feature-rich, premium e-commerce platform built to provide a seamless shopping experience. Designed with a "Quiet Luxury" aesthetic, the platform handles everything from product discovery and cart management to secure payments and order tracking. 

The application is powered by a robust **Django** backend for secure data handling and business logic, combined with a responsive, modern frontend styled using **Tailwind CSS** and raw JavaScript. 

---

## ✨ Features

* **User Authentication**: Secure login, signup, and OTP-based email verification.
* **Product Listing & Filtering**: Dynamic product pages with category, size, and price range filters.
* **Cart & Checkout**: Session-based cart management with seamless checkout workflows.
* **Wallet System**: Digital wallet for users to store funds, receive refunds, and make direct purchases.
* **Coupon & Offer System**: Category-wide and product-specific discounts, plus checkout coupon application.
* **Order Management**: Real-time order tracking, cancellation workflows, and per-item return tracking.
* **Referral System**: Earn wallet credits by inviting friends using unique referral codes.
* **Admin Panel**: Comprehensive dashboard for managing products, variants, categories, orders, and sales analytics.

---

## 🛠 Tech Stack

* **Backend**: Django (Python)
* **Frontend**: Tailwind CSS, HTML5, Vanilla JavaScript
* **Database**: SQLite (Development) / PostgreSQL (Production ready)
* **Payment Gateway**: Razorpay Integration
* **Email Service**: SMTP integration for OTPs and invoices

---

## 🚀 Installation

Follow these steps to set up the project locally:

**1. Clone the repository**
```bash
git clone https://github.com/yourusername/outfito.git
cd outfito
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Set up environment variables**
Create a `.env` file in the root directory (see Environment Variables section below).

**5. Apply database migrations**
```bash
python manage.py makemigrations
python manage.py migrate
```

**6. Create a superuser (Admin access)**
```bash
python manage.py createsuperuser
```

**7. Run the development server**
```bash
python manage.py runserver
```

---

## 🔐 Environment Variables

Create a `.env` file in your root directory and configure the following variables:

```env
# Security
SECRET_KEY=your-django-secret-key
DEBUG=True

# Database (Optional if using default SQLite)
DATABASE_URL=postgres://user:password@localhost:5432/outfitodb

# Email Configuration (For OTPs and Notifications)
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Payment Gateway
RAZORPAY_KEY_ID=your-razorpay-key-id
RAZORPAY_KEY_SECRET=your-razorpay-key-secret
```

---

## 📁 Folder Structure

* **`admin_side/`**: Dedicated applications for the admin dashboard (product, category, variant, and coupon management).
* **`user_side/`**: Core user-facing applications (authentication, profile, cart, orders, wallet, wishlist).
* **`templates/`**: Global HTML templates divided logically into `admin/` and `user/` directories.
* **`static/`**: Global static assets including compiled CSS, JS scripts, and images.
* **`media/`**: User-uploaded content (e.g., product images, user avatars).

---

## 📸 Screenshots

*(Replace these links with actual image paths once deployed or pushed to GitHub)*

* ![Home Page](docs/screenshots/home.png)
* ![Product Listing](docs/screenshots/shop.png)
* ![Cart & Checkout](docs/screenshots/checkout.png)
* ![Admin Dashboard](docs/screenshots/admin.png)

---

## 🚀 Future Improvements

* **Deployment**: Containerize the application with Docker and deploy to AWS/DigitalOcean.
* **Payment Improvements**: Add multi-currency support and additional payment gateways (e.g., Stripe, PayPal).
* **Performance**: Implement Redis caching for product listings and Celery for background tasks (e.g., async email sending).

---

## 👤 Author

* **Name**: Safwan
* **GitHub**: [@safwan0848](https://github.com/safwan0848)
