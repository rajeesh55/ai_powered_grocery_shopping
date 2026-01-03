# -*- coding: utf-8 -*-
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import re
import g4f
import uuid
from datetime import datetime
import traceback
import bcrypt  # For password hashing
import os
from functools import wraps  # For auth decorators

app = Flask(__name__)
app.secret_key = os.urandom(24)

# MongoDB config
app.config["MONGO_URI"] = "mongodb://localhost:27017/ingredient_app"
try:
    mongo = PyMongo(app)
    products_col = mongo.db.products
    suggestions_col = mongo.db.suggestions
    orders_col = mongo.db.orders
    users_col = mongo.db.users  # New collection for users
    recipes_col = mongo.db.recipes  # New collection for recipes
    # Test connection
    mongo.cx.server_info()
    print("MongoDB connection successful.")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")

# --- Decorators ---
@app.context_processor
def inject_current_year():
    """Injects the current year into all templates."""
    return {'current_year': datetime.now().year}
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to access this page", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin" not in session or not session["admin"]:
            flash("Admin access required", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# --- User Authentication ---

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Get form data
        name = request.form.get("name").strip()
        username = request.form.get("username").strip().lower()
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        email = request.form.get("email").strip().lower()
        
        # Validation
        if not all([name, username, password, email]):
            flash("All fields are required", "danger")
            return render_template("register.html")
            
        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return render_template("register.html")
        
        # Check if username or email already exists
        if users_col.find_one({"username": username}):
            flash("Username already exists", "danger")
            return render_template("register.html")
            
        if users_col.find_one({"email": email}):
            flash("Email already exists", "danger")
            return render_template("register.html")
        
        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Create user
        new_user = {
            "name": name,
            "username": username,
            "password": hashed_password,
            "email": email,
            "created_at": datetime.now(),
            "is_admin": False  # Default to regular user
        }
        
        users_col.insert_one(new_user)
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))
        
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        username = request.form.get("username").strip().lower()
        password = request.form.get("password")
        
        user = users_col.find_one({"username": username})
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user["password"]):
            # Store user info in session
            session["user_id"] = str(user["_id"])
            session["username"] = user["username"]
            session["name"] = user["name"]
            
            # Check if admin
            if user.get("is_admin", False):
                session["admin"] = True
                
            next_page = request.args.get("next", url_for("dashboard"))
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(next_page)
        else:
            flash("Invalid username or password", "danger")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    # Clear all session data
    session.clear()
    flash("You have been logged out", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get("user_id")
    
    # Get user info
    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        session.clear()
        flash("User not found", "danger")
        return redirect(url_for("login"))
    
    # Get user's orders
    user_orders = list(orders_col.find({"user_id": user_id}).sort("order_date", -1))
    
    return render_template("index.html", 
                          user=user,
                          orders=user_orders)

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = session.get("user_id")
    user = users_col.find_one({"_id": ObjectId(user_id)})
    
    if request.method == "POST":
        # Update profile
        name = request.form.get("name")
        email = request.form.get("email")
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        # Verify current password if provided
        if current_password:
            if not bcrypt.checkpw(current_password.encode('utf-8'), user["password"]):
                flash("Current password is incorrect", "danger")
                return redirect(url_for("profile"))
                
            if new_password != confirm_password:
                flash("New passwords do not match", "danger")
                return redirect(url_for("profile"))
                
            # Update password
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            users_col.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"password": hashed_password}}
            )
            flash("Password updated successfully", "success")
        
        # Update name and email
        update_data = {}
        if name and name != user["name"]:
            update_data["name"] = name
            session["name"] = name
            
        if email and email != user["email"]:
            # Check if email is already taken
            if users_col.find_one({"email": email, "_id": {"$ne": ObjectId(user_id)}}):
                flash("Email already in use", "danger")
                return redirect(url_for("profile"))
            update_data["email"] = email
            
        if update_data:
            users_col.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            flash("Profile updated successfully", "success")
            
        return redirect(url_for("profile"))
    
    return render_template("profile.html", user=user)

# --- Enhanced home page with product listing and search ---

@app.route("/", methods=["GET", "POST"])
def index():
    ingredients = []
    instructions = None
    dish_name = ""
    servings = ""
    matched_products = []
    error_message = None
    
    # Define common dietary preferences
    dietary_options = [
        "Vegetarian",
        "Vegan",
        "Gluten-Free",
        "Dairy-Free",
        "Keto",
        "Paleo",
        "Low-Carb",
        "Nut-Free"
    ]
    
    # For product search
    search_query = request.args.get("search", "")
    category = request.args.get("category", "")
    
    # Get available product categories
    try:
        categories = products_col.distinct("category")
    except Exception as e:
        print(f"Error fetching categories: {e}")
        categories = []
    
    if request.method == "POST":
        dish_name = request.form.get("dish_name", "").strip()
        servings = request.form.get("servings", "").strip()
        # Get selected dietary preferences
        dietary_preferences = request.form.getlist("dietary_preferences")

        if not dish_name:
            flash("Please enter a dish name.", "warning")
        elif not servings:
            flash("Please enter the number of servings.", "warning")
        else:
            ingredients, instructions, error_message = get_scaled_ingredients(dish_name, servings, dietary_preferences)

            if error_message:
                flash(error_message, "danger")

            if isinstance(ingredients, list):
                # Store suggestion if user is logged in
                if "user_id" in session:
                    try:
                        suggestions_col.insert_one({
                            "user_id": session["user_id"],
                            "dish_name": dish_name,
                            "servings": int(servings),
                            "dietary_preferences": dietary_preferences,
                            "ingredients": ingredients,
                            "instructions": instructions,
                            "timestamp": datetime.now()
                        })
                    except Exception as e:
                        print(f"Error saving suggestion to DB: {e}")
                
                # Match ingredients to products
                for ing in ingredients:
                    ingredient_name = ing["name"]
                    ingredient_quantity = ing["quantity"]
                    ingredient_name_norm = normalize_ingredient_name(ingredient_name)

                    # Find matching product
                    product = find_matching_product(ingredient_name_norm)
                    
                    if product:
                        product_name_db = product.get("name", "N/A")
                        image_url_db = product.get("image_url", url_for('static', filename='images/default.png'))
                        price = calculate_price(product_name_db, ingredient_quantity)

                        matched_products.append({
                            "ingredient_name": ingredient_name,
                            "quantity": ingredient_quantity,
                            "product_name": product_name_db,
                            "image_url": image_url_db,
                            "price": price,
                            "product_id": str(product["_id"])
                        })
                    else:
                        # Log unmatched ingredient
                        print(f"No match found for ingredient: '{ingredient_name}'")
                        if "user_id" in session:
                            try:
                                suggestions_col.insert_one({
                                    "user_id": session["user_id"],
                                    "ingredient_name": ingredient_name,
                                    "normalized_name": ingredient_name_norm,
                                    "quantity": ingredient_quantity,
                                    "dish": dish_name,
                                    "status": "unmatched",
                                    "timestamp": datetime.now()
                                })
                            except Exception as e:
                                print(f"Error saving unmatched suggestion: {e}")

    # Get products based on search/filter or just get all
    try:
        products_query = {}
        
        if search_query:
            # Search in name, description, and tags
            products_query["$or"] = [
                {"name": {"$regex": search_query, "$options": "i"}},
                {"description": {"$regex": search_query, "$options": "i"}},
                {"tags": {"$regex": search_query, "$options": "i"}}
            ]
            
        if category:
            products_query["category"] = category
            
        all_products = list(products_col.find(products_query).sort("name", 1))
    except Exception as e:
        print(f"Error fetching products: {e}")
        flash("Could not load product list.", "danger")
        all_products = []

    return render_template("index.html",
                           ingredients=ingredients,
                           instructions=instructions,
                           matched_products=matched_products,
                           dish_name=dish_name,
                           servings=servings,
                           products=all_products,
                           categories=categories,
                           search_query=search_query,
                           current_category=category,
                           error_message=error_message,
                           dietary_options=dietary_options)

def find_matching_product(ingredient_name_norm):
    """Find matching product using multiple methods"""
    # Direct match by normalized name
    product = products_col.find_one({"name_normalized": ingredient_name_norm})
    if product:
        return product
        
    # Try synonym lookup
    for key, synonyms in INGREDIENT_SYNONYMS.items():
        if ingredient_name_norm == key or ingredient_name_norm in synonyms:
            canonical_name = key
            product = products_col.find_one({"name_normalized": canonical_name})
            if product:
                return product
    
    # Fuzzy match with regex
    safe_name_pattern = re.escape(ingredient_name_norm)
    product = products_col.find_one({
        "name": re.compile(f".*{safe_name_pattern}.*", re.IGNORECASE)
    })
    if product:
        return product
        
    return None

# --- Enhanced Cart Functions ---

@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    try:
        product_name = request.form["product_name"]
        ingredient_name = request.form.get("ingredient_name", product_name)
        recipe_quantity = request.form.get("quantity", "")
        image_url = request.form.get("image_url", url_for('static', filename='images/default.png'))
        product_id = request.form.get("product_id")
        
        # Get product details
        product_data = None
        if product_id:
            product = products_col.find_one({"_id": ObjectId(product_id)})
            if product:
                product_data = product
                product_name = product.get("name", product_name)
                image_url = product.get("image_url", image_url)
        
        # If no product found by ID, try finding by name
        if not product_data:
            norm_name = normalize_ingredient_name(product_name)
            product_key = find_product_key(norm_name)
            if product_key and product_key in PRODUCT_INFO:
                product_data = PRODUCT_INFO[product_key]
                db_product = products_col.find_one({"name_normalized": product_key})
                if db_product:
                    product_name = db_product.get("name", product_name)
                    image_url = db_product.get("image_url", image_url)
                    product_id = str(db_product["_id"])
        
        if not product_data:
            flash(f"Could not find product information for '{product_name}'", "warning")
            return redirect(request.referrer or url_for('index'))
        
        # Determine quantity and calculate price
        unit = product_data.get("unit", "unit")
        min_qty = product_data.get("min_qty", 1)
        default_qty = product_data.get("default_qty", f"{min_qty} {unit}")
        
        # Use recipe quantity if valid, otherwise use default
        quantity_to_add = parse_and_validate_quantity(recipe_quantity, default_qty, min_qty, unit)
        price = calculate_price(product_name, quantity_to_add)
        
        # Create cart item
        item = {
            "id": str(uuid.uuid4()),
            "product_name": product_name,
            "ingredient_name": ingredient_name,
            "quantity": quantity_to_add,
            "image_url": image_url,
            "price": price,
            "unit": unit,
            "min_qty": min_qty,
            "product_id": product_id
        }
        
        # Add to cart or update existing item
        cart = session.get("cart", [])
        if not isinstance(cart, list):
            cart = []
        
        # Check if product already in cart
        for i, cart_item in enumerate(cart):
            if (cart_item.get("product_id") and cart_item.get("product_id") == item["product_id"]) or \
               (not cart_item.get("product_id") and cart_item["product_name"] == item["product_name"]):
                # Update quantity if units match
                try:
                    existing_qty_val, existing_unit = parse_quantity(cart_item["quantity"])
                    new_qty_val, new_unit = parse_quantity(item["quantity"])
                    
                    if existing_unit == new_unit:
                        updated_qty_val = existing_qty_val + new_qty_val
                        cart[i]["quantity"] = f"{updated_qty_val} {existing_unit}"
                        cart[i]["price"] = calculate_price(cart_item["product_name"], cart[i]["quantity"])
                        flash(f"Updated quantity for {cart_item['product_name']} in cart", "success")
                        session["cart"] = cart
                        return redirect(request.referrer or url_for('index'))
                except Exception as e:
                    print(f"Error updating quantity: {e}")
        
        # If not updated, add as new item
        cart.append(item)
        flash(f"Added {item['product_name']} to cart", "success")
        session["cart"] = cart
        
        return redirect(request.referrer or url_for('index'))
    
    except Exception as e:
        flash(f"Error adding item to cart: {e}", "danger")
        print(f"Error in add_to_cart: {traceback.format_exc()}")
        return redirect(request.referrer or url_for('index'))

def parse_and_validate_quantity(recipe_quantity, default_qty, min_qty, base_unit):
    """Parse quantity and ensure it meets minimum requirements"""
    if not recipe_quantity:
        return default_qty
        
    try:
        amount, unit = parse_quantity(recipe_quantity)
        
        # Check if units match or are convertible
        unit_compatible = unit == base_unit or \
                         (unit in ['gm', 'kg'] and base_unit in ['gm', 'kg']) or \
                         (unit in ['ml', 'liter'] and base_unit in ['ml', 'liter']) or \
                         (unit == 'bunch' and base_unit == 'bunch')
                         
        if unit_compatible:
            # Convert to base unit for comparison if needed
            converted_amount = amount
            if unit == 'gm' and base_unit == 'kg':
                converted_amount = amount / 1000
            elif unit == 'kg' and base_unit == 'gm':
                converted_amount = amount * 1000
            elif unit == 'ml' and base_unit == 'liter':
                converted_amount = amount / 1000
            elif unit == 'liter' and base_unit == 'ml':
                converted_amount = amount * 1000
                
            if converted_amount >= min_qty:
                return recipe_quantity
            else:
                return f"{min_qty} {base_unit}"
        else:
            return default_qty
    except Exception:
        return default_qty

@app.route("/cart")
def view_cart():
    cart = session.get("cart", [])
    if not isinstance(cart, list):
        cart = []
    total = sum(item.get("price", 0) for item in cart)
    return render_template("cart.html", cart=cart, total=total)

@app.route("/update_cart", methods=["POST"])
def update_cart():
    cart = session.get("cart", [])
    if not isinstance(cart, list):
        cart = []
        
    try:
        item_id = request.form["item_id"]
        new_quantity = float(request.form["quantity"])
        
        for item in cart:
            if item.get("id") == item_id:
                unit = item.get("unit", "unit")
                min_qty = item.get("min_qty", 0)
                
                if new_quantity < min_qty:
                    flash(f"Minimum quantity for {item['product_name']} is {min_qty} {unit}", "warning")
                elif new_quantity == 0:
                    return redirect(url_for('remove_from_cart', item_id=item_id))
                else:
                    item["quantity"] = f"{new_quantity} {unit}"
                    item["price"] = calculate_price(item["product_name"], item["quantity"])
                    flash(f"Updated quantity for {item['product_name']}", "success")
                break
                
        session["cart"] = cart
    except ValueError:
        flash("Invalid quantity format", "danger")
    except Exception as e:
        flash(f"Error updating cart: {e}", "danger")
        print(f"Error updating cart: {e}")
        
    return redirect(url_for("view_cart"))

@app.route("/remove_from_cart/<item_id>")
def remove_from_cart(item_id):
    cart = session.get("cart", [])
    if not isinstance(cart, list):
        cart = []
        
    original_length = len(cart)
    cart = [item for item in cart if item.get("id") != item_id]
    
    if len(cart) < original_length:
        flash("Item removed from cart", "success")
    else:
        flash("Item not found in cart", "warning")
        
    session["cart"] = cart
    return redirect(url_for("view_cart"))

# --- Enhanced Checkout ---

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = session.get("cart", [])
    if not isinstance(cart, list):
        cart = []
    if not cart:
        flash("Your cart is empty", "warning")
        return redirect(url_for("index"))
        
    total = sum(item.get("price", 0) for item in cart)
    
    # Pre-fill form with user info if logged in
    user_data = {}
    if "user_id" in session:
        user = users_col.find_one({"_id": ObjectId(session["user_id"])})
        if user:
            user_data = {
                "name": user.get("name", ""),
                "email": user.get("email", ""),
                # Phone and address would be here if stored in user profile
            }
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        phone = request.form.get("phone", "").strip()
        
        if not all([name, email, address, phone]):
            flash("Please fill in all required fields", "danger")
            return render_template("checkout.html", cart=cart, total=total,
                                  name=name, email=email, address=address, phone=phone)
                                  
        try:
            order = {
                "order_id": str(uuid.uuid4()),
                "order_date": datetime.now(),
                "items": cart,
                "total": total,
                "customer_name": name,
                "customer_email": email,
                "customer_address": address,
                "customer_phone": phone,
                "status": "pending"
            }
            
            # Add user_id if logged in
            if "user_id" in session:
                order["user_id"] = session["user_id"]
                
            # Insert order
            insert_result = orders_col.insert_one(order)
            print(f"Order {order['order_id']} inserted with DB ID: {insert_result.inserted_id}")
            
            # Clear cart
            session.pop("cart", None)
            
            flash("Order placed successfully!", "success")
            
            return render_template("order_confirmation.html", order=order)
            
        except Exception as e:
            flash(f"An error occurred during checkout: {e}", "danger")
            print(f"Error in checkout: {traceback.format_exc()}")
            return render_template("checkout.html", cart=cart, total=total,
                                  name=name, email=email, address=address, phone=phone)
    
    return render_template("checkout.html", cart=cart, total=total, **user_data)

# --- Admin Panel ---

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_panel"))
        
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        admin_user = users_col.find_one({"username": username, "is_admin": True})
        
        if admin_user and bcrypt.checkpw(password.encode('utf-8'), admin_user["password"]):
            session["admin"] = True
            session["user_id"] = str(admin_user["_id"])
            session["username"] = admin_user["username"]
            session["name"] = admin_user["name"]
            flash("Admin login successful!", "success")
            return redirect(url_for("admin_panel"))
        else:
            flash("Invalid admin credentials", "danger")
            
    return render_template("admin_login.html")

@app.route("/admin/panel", methods=["GET", "POST"])
@admin_required
def admin_panel():
    if request.method == "POST":
        # Add product logic
        name = request.form.get("product_name", "").strip()
        image_url = request.form.get("image_url", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        tags = request.form.get("tags", "").strip()
        
        if not name or not image_url:
            flash("Product name and image URL are required", "warning")
        else:
            try:
                price_per_unit = float(request.form.get("price_per_unit", 0))
                unit = request.form.get("unit", "unit").lower().strip()
                min_qty = float(request.form.get("min_qty", 1))
                
                # Normalize name
                name_normalized = normalize_ingredient_name(name)
                
                # Create tags list
                tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
                
                # Insert product
                products_col.insert_one({
                    "name": name,
                    "name_normalized": name_normalized,
                    "image_url": image_url,
                    "category": category,
                    "description": description,
                    "tags": tags_list,
                    "price_per_unit": price_per_unit,
                    "unit": unit,
                    "min_qty": min_qty,
                    "added_date": datetime.now()
                })
                
                flash(f"Product '{name}' added successfully", "success")
                
                # Update PRODUCT_INFO dictionary
                if name_normalized not in PRODUCT_INFO:
                    PRODUCT_INFO[name_normalized] = {
                        "default_qty": f"1 {unit}",
                        "unit": unit,
                        "price_per_unit": price_per_unit,
                        "min_qty": min_qty
                    }
                    
            except ValueError:
                flash("Invalid number format for price or minimum quantity", "danger")
            except Exception as e:
                flash(f"Error adding product: {e}", "danger")
                print(f"Error adding product: {e}")
                
        return redirect(url_for('admin_panel'))
        
    # Get data for display
    try:
        products = list(products_col.find().sort("name", 1))
        unmatched_suggestions = list(suggestions_col.find({"status": "unmatched"}).sort("timestamp", -1))
        recent_orders = list(orders_col.find().sort("order_date", -1).limit(10))
        categories = products_col.distinct("category")
    except Exception as e:
        flash(f"Error fetching data: {e}", "danger")
        products = []
        unmatched_suggestions = []
        recent_orders = []
        categories = []
        
    return render_template("admin_panel.html",
                          products=products,
                          unmatched_suggestions=unmatched_suggestions,
                          orders=recent_orders,
                          categories=categories)

@app.route("/admin/orders")
@admin_required
def view_orders():
    try:
        status_filter = request.args.get("status", "")
        customer_filter = request.args.get("customer", "")
        
        query = {}
        if status_filter:
            query["status"] = status_filter
        if customer_filter:
            query["customer_name"] = {"$regex": customer_filter, "$options": "i"}
            
        orders = list(orders_col.find(query).sort("order_date", -1))
        
        # Get distinct statuses for filtering
        statuses = orders_col.distinct("status")
    except Exception as e:
        flash(f"Error fetching orders: {e}", "danger")
        print(f"Error fetching orders: {e}")
        orders = []
        statuses = []
        
    return render_template("orders.html", 
                          orders=orders, 
                          statuses=statuses,
                          current_status=status_filter,
                          customer_filter=customer_filter)

@app.route("/admin/order/<order_id>")
@admin_required
def view_order(order_id):
    try:
        order = orders_col.find_one({"order_id": order_id})
        if not order:
            flash("Order not found", "warning")
            return redirect(url_for("view_orders"))
            
        # Get user details if order has user_id
        user = None
        if "user_id" in order:
            user = users_col.find_one({"_id": ObjectId(order["user_id"])})
            
    except Exception as e:
        flash(f"Error fetching order details: {e}", "danger")
        print(f"Error fetching order {order_id}: {e}")
        return redirect(url_for("view_orders"))
        
    return render_template("order_detail.html", order=order, user=user)

@app.route("/update_order_status/<order_id>/<status>")
@admin_required
def update_order_status(order_id, status):
    valid_statuses = ["pending", "processing", "shipped", "completed", "cancelled"]
    if status not in valid_statuses:
        flash(f"Invalid status '{status}'", "warning")
        return redirect(url_for("view_orders"))
        
    try:
        result = orders_col.update_one(
            {"order_id": order_id},
            {"$set": {"status": status, "last_updated": datetime.now()}}
        )
        
        if result.matched_count == 1:
            if result.modified_count == 1:
                flash(f"Order status updated to '{status}'", "success")
            else:
                flash(f"Order status was already '{status}'", "info")
        else:
            flash("Order not found", "warning")
    except Exception as e:
        flash(f"Error updating order status: {e}", "danger")
        print(f"Error updating status for order {order_id}: {e}")


@app.route("/admin/products")
@admin_required
def manage_products():
    try:
        search_query = request.args.get("search", "")
        category_filter = request.args.get("category", "")
        
        # Build query
        query = {}
        if search_query:
            query["$or"] = [
                {"name": {"$regex": search_query, "$options": "i"}},
                {"description": {"$regex": search_query, "$options": "i"}},
                {"tags": {"$regex": search_query, "$options": "i"}}
            ]
        
        if category_filter:
            query["category"] = category_filter
            
        # Fetch products
        products = list(products_col.find(query).sort("name", 1))
        categories = products_col.distinct("category")
        
    except Exception as e:
        flash(f"Error fetching products: {e}", "danger")
        print(f"Error in manage_products: {traceback.format_exc()}")
        products = []
        categories = []
        
    return render_template("manage_products.html", 
                          products=products,
                          categories=categories,
                          search_query=search_query,
                          current_category=category_filter)

@app.route("/admin/product/edit/<product_id>", methods=["GET", "POST"])
@admin_required
def edit_product(product_id):
    try:
        product = products_col.find_one({"_id": ObjectId(product_id)})
        if not product:
            flash("Product not found", "warning")
            return redirect(url_for("manage_products"))
            
        if request.method == "POST":
            # Get form data
            name = request.form.get("product_name", "").strip()
            image_url = request.form.get("image_url", "").strip()
            category = request.form.get("category", "").strip()
            description = request.form.get("description", "").strip()
            tags = request.form.get("tags", "").strip()
            
            if not name or not image_url:
                flash("Product name and image URL are required", "warning")
                return render_template("edit_product.html", product=product)
                
            try:
                price_per_unit = float(request.form.get("price_per_unit", 0))
                unit = request.form.get("unit", "unit").lower().strip()
                min_qty = float(request.form.get("min_qty", 1))
                
                # Normalize name
                name_normalized = normalize_ingredient_name(name)
                
                # Create tags list
                tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
                
                # Update product
                products_col.update_one(
                    {"_id": ObjectId(product_id)},
                    {"$set": {
                        "name": name,
                        "name_normalized": name_normalized,
                        "image_url": image_url,
                        "category": category,
                        "description": description,
                        "tags": tags_list,
                        "price_per_unit": price_per_unit,
                        "unit": unit,
                        "min_qty": min_qty,
                        "last_updated": datetime.now()
                    }}
                )
                
                flash(f"Product '{name}' updated successfully", "success")
                
                # Update PRODUCT_INFO dictionary
                PRODUCT_INFO[name_normalized] = {
                    "default_qty": f"1 {unit}",
                    "unit": unit,
                    "price_per_unit": price_per_unit,
                    "min_qty": min_qty
                }
                
                return redirect(url_for("manage_products"))
                
            except ValueError:
                flash("Invalid number format for price or minimum quantity", "danger")
            except Exception as e:
                flash(f"Error updating product: {e}", "danger")
                print(f"Error updating product: {traceback.format_exc()}")
            
    except Exception as e:
        flash(f"Error fetching product details: {e}", "danger")
        print(f"Error in edit_product: {traceback.format_exc()}")
        return redirect(url_for("manage_products"))
        
    # Get categories for dropdown
    categories = products_col.distinct("category")
    
    return render_template("edit_product.html", product=product, categories=categories)

@app.route("/admin/product/delete/<product_id>", methods=["POST"])
@admin_required
def delete_product(product_id):
    try:
        product = products_col.find_one({"_id": ObjectId(product_id)})
        if not product:
            flash("Product not found", "warning")
            return redirect(url_for("manage_products"))
            
        # Delete product
        products_col.delete_one({"_id": ObjectId(product_id)})
        
        # Remove from PRODUCT_INFO if present
        name_normalized = product.get("name_normalized")
        if name_normalized and name_normalized in PRODUCT_INFO:
            del PRODUCT_INFO[name_normalized]
            
        flash(f"Product '{product.get('name')}' deleted successfully", "success")
        
    except Exception as e:
        flash(f"Error deleting product: {e}", "danger")
        print(f"Error in delete_product: {traceback.format_exc()}")
        
    return redirect(url_for("manage_products"))

@app.route("/admin/users")
@admin_required
def manage_users():
    try:
        search_query = request.args.get("search", "")
        role_filter = request.args.get("role", "")
        
        # Build query
        query = {}
        if search_query:
            query["$or"] = [
                {"name": {"$regex": search_query, "$options": "i"}},
                {"username": {"$regex": search_query, "$options": "i"}},
                {"email": {"$regex": search_query, "$options": "i"}}
            ]
        
        if role_filter:
            if role_filter == "admin":
                query["is_admin"] = True
            elif role_filter == "user":
                query["is_admin"] = False
                
        # Fetch users
        users = list(users_col.find(query).sort("username", 1))
        
    except Exception as e:
        flash(f"Error fetching users: {e}", "danger")
        print(f"Error in manage_users: {traceback.format_exc()}")
        users = []
        
    return render_template("manage_users.html", 
                          users=users,
                          search_query=search_query,
                          role_filter=role_filter)

@app.route("/admin/user/<user_id>", methods=["GET", "POST"])
@admin_required
def edit_user(user_id):
    try:
        user = users_col.find_one({"_id": ObjectId(user_id)})
        if not user:
            flash("User not found", "warning")
            return redirect(url_for("manage_users"))
            
        if request.method == "POST":
            # Get form data
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            is_admin = request.form.get("is_admin") == "on"
            new_password = request.form.get("new_password", "").strip()
            
            if not name or not email:
                flash("Name and email are required", "warning")
                return render_template("edit_user.html", user=user)
                
            # Check if email already exists for another user
            if email != user["email"] and users_col.find_one({"email": email, "_id": {"$ne": ObjectId(user_id)}}):
                flash("Email already in use by another account", "danger")
                return render_template("edit_user.html", user=user)
                
            # Update user
            update_data = {
                "name": name,
                "email": email,
                "is_admin": is_admin,
                "last_updated": datetime.now()
            }
            
            # Update password if provided
            if new_password:
                hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
                update_data["password"] = hashed_password
                
            users_col.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": update_data}
            )
            
            flash(f"User '{user['username']}' updated successfully", "success")
            return redirect(url_for("manage_users"))
            
    except Exception as e:
        flash(f"Error managing user: {e}", "danger")
        print(f"Error in edit_user: {traceback.format_exc()}")
        return redirect(url_for("manage_users"))
        
    return render_template("edit_user.html", user=user)

# --- Product browsing and details ---

@app.route("/products")
def browse_products():
    search_query = request.args.get("search", "")
    category = request.args.get("category", "")
    
    try:
        # Build query
        query = {}
        if search_query:
            query["$or"] = [
                {"name": {"$regex": search_query, "$options": "i"}},
                {"description": {"$regex": search_query, "$options": "i"}},
                {"tags": {"$regex": search_query, "$options": "i"}}
            ]
            
        if category:
            query["category"] = category
            
        # Pagination
        page = int(request.args.get("page", 1))
        per_page = 12
        skip = (page - 1) * per_page
        
        # Fetch products
        products = list(products_col.find(query).sort("name", 1).skip(skip).limit(per_page))
        total_products = products_col.count_documents(query)
        total_pages = (total_products + per_page - 1) // per_page
        
        # Get categories for sidebar
        categories = products_col.distinct("category")
        
    except Exception as e:
        flash(f"Error fetching products: {e}", "danger")
        print(f"Error in browse_products: {traceback.format_exc()}")
        products = []
        categories = []
        total_pages = 1
        
    return render_template("browse_products.html",
                          products=products,
                          categories=categories,
                          search_query=search_query,
                          current_category=category,
                          page=page,
                          total_pages=total_pages)

@app.route("/product/<product_id>")
def product_detail(product_id):
    try:
        product = products_col.find_one({"_id": ObjectId(product_id)})
        if not product:
            flash("Product not found", "warning")
            return redirect(url_for("browse_products"))
            
        # Get related products in same category
        related_products = list(products_col.find({
            "category": product["category"],
            "_id": {"$ne": ObjectId(product_id)}
        }).limit(4))
        
    except Exception as e:
        flash(f"Error fetching product details: {e}", "danger")
        print(f"Error in product_detail: {traceback.format_exc()}")
        return redirect(url_for("browse_products"))
        
    return render_template("product_detail.html", product=product, related_products=related_products)

# --- Helper functions ---

def get_scaled_ingredients(dish_name, servings, dietary_preferences=None):
    """Get ingredients for a dish and scale them for the number of servings, considering dietary preferences"""
    if not dish_name or not servings:
        return [], None, "Missing dish name or servings"
        
    try:
        servings = int(servings)
        if servings <= 0 or servings > 20:
            return [], None, "Please enter a number of servings between 1 and 20"
    except ValueError:
        return [], None, "Invalid number format for servings"
        
    try:
        # Build dietary restrictions string if needed
        dietary_str = ""
        if dietary_preferences:
            dietary_str = f" The recipe must follow these dietary restrictions: {', '.join(dietary_preferences)}. Please provide suitable alternatives for any restricted ingredients."
            
        # Build prompt for AI
        prompt = f"""I need the ingredients for {dish_name} scaled for {servings} servings.{dietary_str}
        Format as a JSON array of objects, each with 'name' and 'quantity' properties.
        Don't include instructions or additional explanation.
        Example format: 
        [
          {{"name": "tomatoes", "quantity": "2 medium"}},
          {{"name": "olive oil", "quantity": "3 tbsp"}}
        ]"""
        
        # Use GPT-4 with default provider
        response = g4f.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        
        if response:
            # Clean up the response
            response = response.strip()
            
            # Find JSON content
            start_idx = response.find('[')
            end_idx = response.rfind(']')
            
            if start_idx != -1 and end_idx != -1:
                json_str = response[start_idx:end_idx + 1]
                
                try:
                    # Parse the JSON string
                    import json
                    ingredients = json.loads(json_str)
                    
                    # Validate the structure
                    if not isinstance(ingredients, list):
                        return [], None, "Invalid response format"
                    
                    # Since we're not getting instructions anymore, return empty list for instructions
                    return ingredients, [], None
                        
                except json.JSONDecodeError as e:
                    print(f"JSON parsing error: {e}")
                    return [], None, "Error parsing recipe data"
                    
        return [], None, "Unable to generate recipe at this time. Please try again later."
            
    except Exception as e:
        error_msg = f"Error in recipe generation: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        return [], None, error_msg

def normalize_ingredient_name(name):
    """Normalize ingredient name for consistent lookup"""
    if not name:
        return ""
        
    # Convert to lowercase
    name = name.lower()
    
    # Remove common words like "fresh", "dried", etc.
    for word in ["fresh", "dried", "frozen", "canned", "whole", "sliced", "diced", "chopped", "minced"]:
        name = re.sub(r'\b' + word + r'\b', '', name)
    
    # Remove measurements
    name = re.sub(r'\d+(\.\d+)?\s*(oz|ounce|lb|pound|g|gram|kg|cup|tbsp|tsp|tablespoon|teaspoon)', '', name)
    
    # Clean up extra spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Handle plural forms - common cases
    name = re.sub(r'(\w+)ies$', r'\1y', name)  # berries -> berry
    name = re.sub(r'(\w+)oes$', r'\1o', name)  # tomatoes -> tomato
    name = re.sub(r'(\w+[^s])s$', r'\1', name)  # onions -> onion
    
    return name

# Define ingredient synonyms for matching
INGREDIENT_SYNONYMS = {
    "tomato": ["roma tomato", "cherry tomato", "plum tomato"],
    "onion": ["red onion", "white onion", "yellow onion", "spring onion", "scallion"],
    "potato": ["russet potato", "yukon gold potato", "red potato", "sweet potato"],
    "pepper": ["bell pepper", "red pepper", "green pepper", "yellow pepper", "chili pepper"],
    "oil": ["olive oil", "vegetable oil", "canola oil", "cooking oil"],
    "rice": ["white rice", "brown rice", "jasmine rice", "basmati rice"],
    "flour": ["all-purpose flour", "bread flour", "cake flour", "wheat flour"],
    # Add more synonyms as needed
}

# Placeholder for PRODUCT_INFO (replace with DB in production)
PRODUCT_INFO = {
    "tomato": {"default_qty": "500 gm", "unit": "gm", "price_per_unit": 0.002, "min_qty": 500},
    "onion": {"default_qty": "250 gm", "unit": "gm", "price_per_unit": 0.0015, "min_qty": 250},
    "potato": {"default_qty": "1 kg", "unit": "kg", "price_per_unit": 1.2, "min_qty": 1},
    "carrot": {"default_qty": "500 gm", "unit": "gm", "price_per_unit": 0.0018, "min_qty": 500},
    "flour": {"default_qty": "1 kg", "unit": "kg", "price_per_unit": 0.8, "min_qty": 1},
    "rice": {"default_qty": "1 kg", "unit": "kg", "price_per_unit": 1.5, "min_qty": 1},
    "milk": {"default_qty": "1 liter", "unit": "liter", "price_per_unit": 1.2, "min_qty": 1},
    "egg": {"default_qty": "12 unit", "unit": "unit", "price_per_unit": 0.25, "min_qty": 6},
    # Add more products as needed
}

def find_product_key(ingredient_name_norm):
    """Find the product key for an ingredient"""
    # Direct match
    if ingredient_name_norm in PRODUCT_INFO:
        return ingredient_name_norm
        
    # Check synonyms
    for key, synonyms in INGREDIENT_SYNONYMS.items():
        if ingredient_name_norm == key or ingredient_name_norm in synonyms:
            return key
            
    # Partial match (e.g., "roma tomato" matches "tomato")
    for key in PRODUCT_INFO.keys():
        if key in ingredient_name_norm or ingredient_name_norm in key:
            return key
            
    return None

def parse_quantity(quantity_str):
    """Parse quantity string into value and unit"""
    if not quantity_str:
        return 1, "unit"
        
    # Extract numeric value and unit
    match = re.match(r'([\d.]+)\s*([a-zA-Z]*)', quantity_str)
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower().strip() or "unit"
        return value, unit
    else:
        return 1, "unit"

def calculate_price(product_name, quantity):
    """Calculate price based on product and quantity"""
    try:
        norm_name = normalize_ingredient_name(product_name)
        product_key = find_product_key(norm_name)
        
        if not product_key or product_key not in PRODUCT_INFO:
            # Check in database
            product = products_col.find_one({"name_normalized": norm_name})
            if product:
                qty_value, qty_unit = parse_quantity(quantity)
                return round(qty_value * product.get("price_per_unit", 1), 2)
            return 0.99  # Default price if not found
            
        product_info = PRODUCT_INFO[product_key]
        qty_value, qty_unit = parse_quantity(quantity)
        
        # Convert units if necessary
        if qty_unit == "kg" and product_info["unit"] == "gm":
            qty_value *= 1000
        elif qty_unit == "gm" and product_info["unit"] == "kg":
            qty_value /= 1000
        elif qty_unit == "liter" and product_info["unit"] == "ml":
            qty_value *= 1000
        elif qty_unit == "ml" and product_info["unit"] == "liter":
            qty_value /= 1000
            
        # Calculate price
        return round(qty_value * product_info["price_per_unit"], 2)
    
    except Exception as e:
        print(f"Error calculating price: {e}")
        return 0.99  # Default price on error

# --- API endpoints for AJAX calls ---

@app.route("/api/products/search", methods=["GET"])
def api_search_products():
    try:
        query = request.args.get("q", "").strip()
        category = request.args.get("category", "")
        
        db_query = {}
        if query:
            db_query["$or"] = [
                {"name": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}},
                {"tags": {"$regex": query, "$options": "i"}}
            ]
            
        if category:
            db_query["category"] = category
            
        products = list(products_col.find(db_query).limit(20))
        
        # Format for JSON response
        result = []
        for product in products:
            result.append({
                "id": str(product["_id"]),
                "name": product["name"],
                "image_url": product["image_url"],
                "category": product["category"],
                "price": calculate_price(product["name"], product.get("default_qty", f"1 {product.get('unit', 'unit')}")),
                "unit": product.get("unit", "unit")
            })
            
        return jsonify({"success": True, "products": result})
    except Exception as e:
        print(f"Error in API search: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/order/<order_id>/status", methods=["POST"])
@login_required
def api_update_order_status(order_id):
    try:
        # Check admin status
        if not session.get("admin"):
            return jsonify({"success": False, "error": "Permission denied"})
            
        status = request.json.get("status")
        if not status:
            return jsonify({"success": False, "error": "No status provided"})
            
        valid_statuses = ["pending", "processing", "shipped", "completed", "cancelled"]
        if status not in valid_statuses:
            return jsonify({"success": False, "error": f"Invalid status '{status}'"})
            
        # Update order
        result = orders_col.update_one(
            {"order_id": order_id},
            {"$set": {"status": status, "last_updated": datetime.now()}}
        )
        
        if result.matched_count == 0:
            return jsonify({"success": False, "error": "Order not found"})
            
        return jsonify({
            "success": True, 
            "message": f"Order status updated to '{status}'",
            "status": status
        })
        
    except Exception as e:
        print(f"Error updating order status: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)})

# --- Error handlers ---

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# --- Initialize database with some data if empty ---

def init_db():
    """Initialize database with admin user only"""
    try:
        # Check if admin user exists
        if users_col.count_documents({"is_admin": True}) == 0:
            print("Creating admin user...")
            hashed_password = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt())
            
            admin_user = {
                "name": "Admin User",
                "username": "admin",
                "password": hashed_password,
                "email": "admin@example.com",
                "created_at": datetime.now(),
                "is_admin": True
            }
            
            users_col.insert_one(admin_user)
            print("Admin user created with username 'admin' and password 'admin123'")
            
    except Exception as e:
        print(f"Error initializing database: {e}")
        print(traceback.format_exc())

@app.route("/recipes")
def recipes():
    search_query = request.args.get("search", "")
    difficulty = request.args.get("difficulty", "")
    dietary = request.args.getlist("dietary")
    
    try:
        # Build query
        query = {}
        if search_query:
            query["$or"] = [
                {"name": {"$regex": search_query, "$options": "i"}},
                {"description": {"$regex": search_query, "$options": "i"}},
                {"ingredients.name": {"$regex": search_query, "$options": "i"}}
            ]
            
        if difficulty:
            query["difficulty"] = difficulty
            
        if dietary:
            query["dietary_tags"] = {"$all": dietary}
            
        # Fetch recipes
        recipes = list(recipes_col.find(query).sort("name", 1))
        
        # Get all unique dietary preferences for filter
        dietary_preferences = recipes_col.distinct("dietary_tags")
        if not dietary_preferences:
            dietary_preferences = [
                "Vegetarian", "Vegan", "Gluten-Free", "Dairy-Free",
                "Keto", "Paleo", "Low-Carb", "Nut-Free"
            ]
        
    except Exception as e:
        flash(f"Error fetching recipes: {e}", "danger")
        print(f"Error in recipes: {traceback.format_exc()}")
        recipes = []
        dietary_preferences = []
        
    return render_template("recipes.html",
                          recipes=recipes,
                          search_query=search_query,
                          difficulty=difficulty,
                          dietary_preferences=dietary_preferences,
                          selected_preferences=dietary)

@app.route("/recipe/<recipe_id>")
def recipe_detail(recipe_id):
    try:
        recipe = recipes_col.find_one({"_id": ObjectId(recipe_id)})
        if not recipe:
            flash("Recipe not found", "warning")
            return redirect(url_for("recipes"))
            
        # Get related recipes with similar tags
        related_recipes = list(recipes_col.find({
            "_id": {"$ne": ObjectId(recipe_id)},
            "dietary_tags": {"$in": recipe.get("dietary_tags", [])}
        }).limit(3))
        
        # Get required products
        required_products = []
        for ingredient in recipe.get("ingredients", []):
            product = products_col.find_one({"name_normalized": normalize_ingredient_name(ingredient["name"])})
            if product:
                required_products.append({
                    "ingredient": ingredient,
                    "product": product
                })
        
    except Exception as e:
        flash(f"Error fetching recipe details: {e}", "danger")
        print(f"Error in recipe_detail: {traceback.format_exc()}")
        return redirect(url_for("recipes"))
        
    return render_template("recipe_detail.html", 
                          recipe=recipe,
                          related_recipes=related_recipes,
                          required_products=required_products)

@app.route('/about')
def about():
    return render_template('about.html', current_year=datetime.now().year)

if __name__ == "__main__":
    # Initialize database
    with app.app_context():
        init_db()
        
    # Run application
    app.run(debug=True, host="0.0.0.0", port=8000)