```markdown
# 🧠 EFFZEE – Smart Ingredient Recommender System

EFFZEE is a full-stack AI-powered grocery assistant that helps users generate recipes, view personalized ingredient lists, and shop for the ingredients—all based on their unique health profiles. The app uses OpenAI's GPT-4 for recipe generation and integrates user/admin dashboards, authentication, cart, and order management.

---

## 🌟 Features

### 👤 User Panel
- 🍽️ Generate recipes using GPT-4
- 🧾 View and save ingredient lists
- 🛒 Add items to cart and place orders
- 🧍 Profile management
- 📦 View order history

### 🔑 Admin Panel
- 👥 Manage users and vendors
- 📦 View, approve, or reject orders
- 🛍️ Manage product listings and categories

### 🧠 Smart Recommendation
- ⚕️ Personalized ingredient suggestions based on health conditions (e.g., diabetes, hypertension)
- 📊 GPT-4 prompts tailored to dietary needs

---

## 🛠️ Tech Stack

| Layer         | Tech Used                                      |
|---------------|------------------------------------------------|
| Frontend      | HTML, CSS, Bootstrap, JavaScript               |
| Backend       | Python (Flask)                                 |
| Database      | MongoDB                                        |
| AI Integration| OpenAI GPT-4 API                               |
| Authentication| Flask-Login, Session-based Auth                |
| Deployment    | (Add here: Render / Heroku / LocalHost)        |

---

## 📁 Project Structure

```

EFFZEE/
├── frontend/
│   ├── user/             # User views
│   ├── admin/            # Admin dashboard
│   ├── static/           # CSS/JS files
│   └── templates/        # HTML templates
├── backend/
│   ├── app.py            # Flask server
│   ├── recommender.py    # GPT-4 integration
│   ├── models/           # MongoDB models
│   └── utils/            # Helper functions
├── .env                  # API keys and config
└── README.md

````

---

## 🚀 How to Run Locally

### Prerequisites
- Python 3.x
- Node.js (if using React in future)
- MongoDB (local or Atlas)
- OpenAI API key

### Installation

```bash
git clone https://github.com/Harikirupa/smart_grocery_assistance.git
cd EFFZEE
pip install -r requirements.txt
````

### Run Flask Server

```bash
python backend/app.py
```

Open browser:

```
http://localhost:5000
```

---

## 🧪 Sample Flow

1. 👤 User logs in
2. 🧠 Enters preferences or selects health condition
3. 🤖 GPT-4 generates a recipe
4. 🧾 App recommends exact ingredients
5. 🛒 User adds to cart and places order
6. 👨‍💼 Admin approves order and manages dispatch

---

## 📈 Future Enhancements

* 📱 Mobile-responsive PWA
* 📦 Vendor-side panel for order fulfillment
* 🗣️ Voice assistant integration for elderly users
* 📍 Location-based vendor recommendations
* 💳 Payment gateway (Razorpay / Stripe)

---

## 🧠 AI Prompt Example

```text
"Generate a simple vegetarian dinner recipe with low sugar content, suitable for a diabetic person. Output ingredients and step-by-step instructions."
```

## 📄 License

This project is for academic purposes and personal learning. Commercial use is restricted unless permission is granted.

---
