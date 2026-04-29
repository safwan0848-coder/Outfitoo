# OUTFITO – Premium E-commerce Platform

A modern, high-performance eCommerce platform built with Django and styled with a "Quiet Luxury" aesthetic using Tailwind CSS. OUTFITO provides a seamless shopping experience with robust backend management, dynamic offers, a wallet system, and secure payment integrations.

---

## 🌟 Features

- **User Authentication:** Secure registration, login, and profile management.
- **Product Listing & Filtering:** Advanced category and product browsing with dynamic filtering.
- **Cart & Checkout:** Intuitive shopping cart with real-time stock validation and offer calculation.
- **Wallet System:** Integrated user wallets for instant refunds and manual top-ups.
- **Coupon & Offer System:** Dynamic product/category offers and user-specific coupon application.
- **Order Management:** Comprehensive order tracking, sequential partial returns, and invoice generation.
- **Admin Panel:** Custom-built, responsive admin dashboard for managing products, categories, orders, offers, and sales analytics.
- **Payment Integration:** Secure checkout and wallet top-ups powered by Razorpay.

---

## 💻 Tech Stack

- **Backend:** Django (Python)
- **Frontend:** HTML5, Tailwind CSS, Vanilla JavaScript
- **Database:** PostgreSQL (Production) / SQLite (Development)
- **Payment Gateway:** Razorpay
- **PDF Generation:** xhtml2pdf (for invoice generation)

---

## 🚀 Installation

Follow these steps to set up the project locally:

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/outfito.git
   cd outfito
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the root directory (where `manage.py` is located) and configure your variables (see below).

5. **Run database migrations**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

6. **Create a superuser (Admin)**
   ```bash
   python manage.py createsuperuser
   ```

7. **Run the development server**
   ```bash
   python manage.py runserver
   ```
   *Access the site at `http://127.0.0.1:8000/` and the admin panel at `http://127.0.0.1:8000/admin/`.*

---

## 🔐 Environment Variables

The project uses `python-dotenv` to manage sensitive configurations. Create a `.env` file in the root directory and include the following:

```env
# Django Settings
SECRET_KEY=your-django-secret-key
DEBUG=True

# Database Configuration (PostgreSQL example)
DB_NAME=outfito_db
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432

# Razorpay Integration
RAZORPAY_KEY_ID=your-razorpay-key-id
RAZORPAY_KEY_SECRET=your-razorpay-key-secret

# Email Settings (for OTP/password reset)
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

---

## 📈 Key Modules

- **Offer Management:** Calculates dynamic "best price" combinations when both category and product offers apply.
- **Refund Engine:** Automatically calculates proportional coupon and offer deductions during sequential partial order returns.
- **Sales Reporting:** Generates interactive admin charts and downloadable PDF/Excel sales reports.

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
