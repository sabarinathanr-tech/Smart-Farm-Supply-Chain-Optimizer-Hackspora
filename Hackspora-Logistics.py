import tkinter as tk
from tkinter import ttk, messagebox
import mysql.connector
import sys
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")
from datetime import datetime
import hashlib
import requests
import random
import webbrowser

DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = "Tvmd@123"
DB_NAME = "farm_supply_chain"

def get_coordinates(location):
    if not location:
        return None, None
    try:
        url = "https://nominatim.openstreetmap.org/search"
        resp = requests.get(url, params={"format": "json", "limit": 1, "q": location}, headers={"User-Agent": "FarmSupplyApp"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            return lat, lon
        return None, None
    except Exception:
        return None, None

def get_location_suggestions(query):
    if not query or len(query.strip()) < 3:
        return []
    try:
        url = "https://nominatim.openstreetmap.org/search"
        resp = requests.get(url, params={"format": "json", "limit": 5, "q": query}, headers={"User-Agent": "FarmSupplyApp"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return [item.get("display_name", "") for item in data]
    except Exception:
        return []

def get_currency_symbol_from_location(text):
    if not text:
        return "₹"
    t = text.lower()
    india_words = [
        "india",
        "tamil nadu",
        "coimbatore",
        "chennai",
        "delhi",
        "mumbai",
        "bangalore",
        "bengaluru",
        "hyderabad",
        "kolkata",
        "pune",
        "kerala",
        "madurai",
        "salem",
    ]
    usa_words = [
        "usa",
        "united states",
        "new york",
        "california",
        "texas",
        "los angeles",
        "chicago",
        "san francisco",
    ]
    europe_words = ["germany", "france", "italy", "spain", "europe", "euro"]
    if any(w in t for w in india_words):
        return "₹"
    if any(w in t for w in usa_words):
        return "$"
    if any(w in t for w in europe_words):
        return "€"
    return "₹"

def upgrade_schema(conn):
    cursor = conn.cursor()

    cursor.execute("SHOW COLUMNS FROM farmers LIKE 'email'")
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE farmers ADD COLUMN email VARCHAR(255)")

    cursor.execute("SHOW COLUMNS FROM farmers LIKE 'latitude'")
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE farmers ADD COLUMN latitude DECIMAL(10,8)")

    cursor.execute("SHOW COLUMNS FROM farmers LIKE 'longitude'")
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE farmers ADD COLUMN longitude DECIMAL(11,8)")

    cursor.execute("SHOW COLUMNS FROM farmers LIKE 'username'")
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE farmers ADD COLUMN username VARCHAR(100) UNIQUE")

    cursor.execute("SHOW COLUMNS FROM farmers LIKE 'password'")
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE farmers ADD COLUMN password VARCHAR(255)")

    cursor.execute("SHOW COLUMNS FROM farmers LIKE 'created_at'")
    if cursor.fetchone() is None:
        cursor.execute(
            "ALTER TABLE farmers ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        )

    cursor.execute("SHOW COLUMNS FROM farmers LIKE 'language'")
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE farmers ADD COLUMN language VARCHAR(50)")

    cursor.execute("SHOW COLUMNS FROM inventory LIKE 'farmer_id'")
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE inventory ADD COLUMN farmer_id INT")

    try:
        cursor.execute("SHOW COLUMNS FROM orders LIKE 'supplier_farmer_id'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE orders ADD COLUMN supplier_farmer_id INT")
    except mysql.connector.Error:
        pass

    conn.commit()
    cursor.close()

def create_all_tables(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS farmers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            contact VARCHAR(20),
            email VARCHAR(255),
            location VARCHAR(255),
            latitude DECIMAL(10, 8),
            longitude DECIMAL(11, 8),
            username VARCHAR(100) UNIQUE,
            password VARCHAR(255),
            language VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_name VARCHAR(255) NOT NULL,
            quantity INT NOT NULL,
            harvest_date DATE NOT NULL,
            farmer_id INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (farmer_id) REFERENCES farmers(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            customer_name VARCHAR(255) NOT NULL,
            product_name VARCHAR(255) NOT NULL,
            quantity INT NOT NULL,
            destination VARCHAR(255) NOT NULL,
            status ENUM('Pending', 'Shipped', 'Delivered') DEFAULT 'Pending',
            supplier_farmer_id INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_farmer_id) REFERENCES farmers(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS logistics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT,
            transport_method ENUM('Truck', 'Van', 'Drone'),
            distance_km FLOAT,
            estimated_cost DECIMAL(10,2),
            estimated_time_hours FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            type ENUM('Truck', 'Van', 'Drone'),
            current_latitude DECIMAL(10, 8),
            current_longitude DECIMAL(11, 8),
            status ENUM('Available', 'In Transit', 'Maintenance') DEFAULT 'Available',
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("SELECT COUNT(*) FROM vehicles")
    count = cursor.fetchone()[0]
    if count == 0:
        cursor.executemany(
            "INSERT INTO vehicles (name, type, current_latitude, current_longitude) VALUES (%s,%s,%s,%s)",
            [
                ("Delivery Truck 1", "Truck", 11.0168, 76.9558),
                ("Delivery Van 1", "Van", 11.1271, 78.6569),
                ("Drone 1", "Drone", 13.0827, 80.2707),
            ],
        )
    upgrade_schema(conn)
    conn.commit()
    cursor.close()

def get_db_connection():
    try:
        conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        cursor.close()
        conn.close()

        conn = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        create_all_tables(conn)
        return conn
    except mysql.connector.Error as err:
        # Log the error to console for easier debugging and also show a messagebox in the UI
        logging.exception("Error connecting to MySQL")
        try:
            # If tkinter is not initialized or running headless, printing to stderr helps capture the issue
            print(f"Database Error: {err}", file=sys.stderr)
        except Exception:
            pass
        try:
            messagebox.showerror("Database Error", f"Error connecting to MySQL: {err}")
        except Exception:
            pass
        return None

class FarmSupplyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Farm Supply Chain & Logistics Optimizer")
        self.root.geometry("1200x800")

        self.colors = {
            "primary": "#4CAF50",
            "secondary": "#FF9800",
            "accent": "#2196F3",
            "background": "#F5F5F5",
            "text": "#212121",
        }

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TNotebook", background=self.colors["background"])
        self.style.configure(
            "TNotebook.Tab",
            background=self.colors["secondary"],
            foreground=self.colors["text"],
            padding=[10, 5],
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.colors["primary"])],
            foreground=[("selected", "white")],
        )
        self.style.configure("TFrame", background=self.colors["background"])
        self.style.configure("TLabel", background=self.colors["background"], foreground=self.colors["text"])
        self.style.configure(
            "TButton",
            background=self.colors["accent"],
            foreground="white",
            padding=5,
            font=("Helvetica", 10),
        )
        self.style.map(
            "TButton",
            background=[("active", self.colors["primary"]), ("pressed", self.colors["secondary"])],
        )

        self.db_connection = get_db_connection()

        self.tab_control = ttk.Notebook(root)
        self.tab_dashboard = ttk.Frame(self.tab_control)
        self.tab_inventory = ttk.Frame(self.tab_control)
        self.tab_orders = ttk.Frame(self.tab_control)
        self.tab_logistics = ttk.Frame(self.tab_control)
        self.tab_farmers = ttk.Frame(self.tab_control)
        self.tab_tracking = ttk.Frame(self.tab_control)

        self.tab_control.add(self.tab_dashboard, text="Dashboard")
        self.tab_control.add(self.tab_inventory, text="Inventory")
        self.tab_control.add(self.tab_orders, text="Orders")
        self.tab_control.add(self.tab_logistics, text="Logistics")
        self.tab_control.add(self.tab_farmers, text="Farmers")
        self.tab_control.add(self.tab_tracking, text="Tracking")
        self.tab_control.pack(expand=1, fill="both")

        self.create_dashboard_tab()
        self.create_inventory_tab()
        self.create_orders_tab()
        self.create_logistics_tab()
        self.create_farmers_tab()
        self.create_tracking_tab()

        if self.db_connection:
            self.load_farmers()
            self.load_farmer_ids()
            self.load_inventory()
            self.load_orders()
            self.load_vehicles()
            self.update_dashboard()

    def execute_query(self, query, params=None, fetch=False):
        if not self.db_connection:
            return None
        try:
            cursor = self.db_connection.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            if fetch:
                data = cursor.fetchall()
                cursor.close()
                return data
            self.db_connection.commit()
            cursor.close()
            return True
        except mysql.connector.Error as err:
            logging.exception("Error executing query")
            try:
                print(f"Database query error: {err}\nQuery: {query}\nParams: {params}", file=sys.stderr)
            except Exception:
                pass
            try:
                messagebox.showerror("Database Error", f"Error executing query: {err}")
            except Exception:
                pass
            return None

    def create_dashboard_tab(self):
        container = tk.Frame(self.tab_dashboard, bg=self.colors["background"])
        container.pack(expand=True, fill="both")

        header = tk.Label(
            container,
            text="Farm Supply Dashboard Overview",
            font=("Arial", 20, "bold"),
            bg=self.colors["primary"],
            fg="white",
            pady=10,
        )
        header.pack(fill="x", pady=(20, 10), padx=40)

        cards_frame = tk.Frame(container, bg=self.colors["background"])
        cards_frame.pack(pady=20)

        card_style = {"relief": "ridge", "bd": 1, "bg": "white", "width": 260, "height": 90}

        self.card_total_products = tk.Frame(cards_frame, **card_style)
        self.card_total_products.grid(row=0, column=0, padx=15, pady=10)

        self.card_total_orders = tk.Frame(cards_frame, **card_style)
        self.card_total_orders.grid(row=0, column=1, padx=15, pady=10)

        self.card_total_farmers = tk.Frame(cards_frame, **card_style)
        self.card_total_farmers.grid(row=1, column=0, padx=15, pady=10)

        self.card_pending_orders = tk.Frame(cards_frame, **card_style)
        self.card_pending_orders.grid(row=1, column=1, padx=15, pady=10)

        self.card_total_units = tk.Frame(cards_frame, **card_style)
        self.card_total_units.grid(row=2, column=0, columnspan=2, padx=15, pady=10)

        self.total_products_label = tk.Label(
            self.card_total_products,
            text="Total Products\n0",
            font=("Arial", 12, "bold"),
            bg="white",
            fg=self.colors["primary"],
        )
        self.total_products_label.place(relx=0.5, rely=0.5, anchor="center")

        self.total_orders_label = tk.Label(
            self.card_total_orders,
            text="Total Orders\n0",
            font=("Arial", 12, "bold"),
            bg="white",
            fg=self.colors["accent"],
        )
        self.total_orders_label.place(relx=0.5, rely=0.5, anchor="center")

        self.total_farmers_label = tk.Label(
            self.card_total_farmers,
            text="Total Farmers\n0",
            font=("Arial", 12, "bold"),
            bg="white",
            fg=self.colors["secondary"],
        )
        self.total_farmers_label.place(relx=0.5, rely=0.5, anchor="center")

        self.pending_orders_label = tk.Label(
            self.card_pending_orders,
            text="Pending Orders\n0",
            font=("Arial", 12, "bold"),
            bg="white",
            fg="#D32F2F",
        )
        self.pending_orders_label.place(relx=0.5, rely=0.5, anchor="center")

        self.total_inventory_units_label = tk.Label(
            self.card_total_units,
            text="Total Inventory Units\n0",
            font=("Arial", 12, "bold"),
            bg="white",
            fg="#6A1B9A",
        )
        self.total_inventory_units_label.place(relx=0.5, rely=0.5, anchor="center")

        tk.Button(
            container,
            text="Refresh Dashboard",
            command=self.update_dashboard,
            bg=self.colors["accent"],
            fg="white",
            font=("Arial", 12, "bold"),
            padx=10,
            pady=5,
        ).pack(pady=(0, 20))

    def update_dashboard(self):
        farmer_id = getattr(self, "farmer_id", None)

        if farmer_id:
            products = self.execute_query(
                "SELECT COUNT(DISTINCT product_name) FROM inventory WHERE farmer_id=%s",
                (farmer_id,),
                fetch=True,
            )
        else:
            products = self.execute_query(
                "SELECT COUNT(DISTINCT product_name) FROM inventory",
                fetch=True,
            )
        if products and products[0][0] is not None:
            self.total_products_label.config(text=f"Total Products\n{products[0][0]}")

        if farmer_id:
            orders = self.execute_query(
                "SELECT COUNT(*) FROM orders WHERE supplier_farmer_id=%s",
                (farmer_id,),
                fetch=True,
            )
            pending = self.execute_query(
                "SELECT COUNT(*) FROM orders WHERE supplier_farmer_id=%s AND status='Pending'",
                (farmer_id,),
                fetch=True,
            )
        else:
            orders = self.execute_query("SELECT COUNT(*) FROM orders", fetch=True)
            pending = self.execute_query(
                "SELECT COUNT(*) FROM orders WHERE status='Pending'",
                fetch=True,
            )

        if orders and orders[0][0] is not None:
            self.total_orders_label.config(text=f"Total Orders\n{orders[0][0]}")
        if pending and pending[0][0] is not None:
            self.pending_orders_label.config(text=f"Pending Orders\n{pending[0][0]}")

        farmers = self.execute_query("SELECT COUNT(*) FROM farmers", fetch=True)
        if farmers and farmers[0][0] is not None:
            self.total_farmers_label.config(text=f"Total Farmers\n{farmers[0][0]}")

        if farmer_id:
            inv_units = self.execute_query(
                "SELECT SUM(quantity) FROM inventory WHERE farmer_id=%s",
                (farmer_id,),
                fetch=True,
            )
        else:
            inv_units = self.execute_query("SELECT SUM(quantity) FROM inventory", fetch=True)

        total_units = inv_units[0][0] if inv_units and inv_units[0][0] is not None else 0
        self.total_inventory_units_label.config(text=f"Total Inventory Units\n{total_units}")

    def create_inventory_tab(self):
        frame = ttk.Frame(self.tab_inventory)
        frame.pack(pady=10, fill="x")

        ttk.Label(frame, text="Product Name").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.inv_name = ttk.Entry(frame, width=20)
        self.inv_name.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Quantity").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        self.inv_qty = ttk.Entry(frame, width=10)
        self.inv_qty.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame, text="Harvest Date (YYYY-MM-DD)").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.inv_date = ttk.Entry(frame, width=15)
        self.inv_date.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Farmer").grid(row=1, column=2, padx=5, pady=5, sticky="e")
        self.inv_farmer_id = ttk.Combobox(frame, width=25, state="readonly")
        self.inv_farmer_id.grid(row=1, column=3, padx=5, pady=5)

        ttk.Button(frame, text="Add Inventory", command=self.add_inventory).grid(row=2, column=0, padx=5, pady=10)
        ttk.Button(frame, text="Refresh", command=self.load_inventory).grid(row=2, column=1, padx=5, pady=10)

        columns = ("id", "name", "qty", "date", "farmer_id", "farmer_name")
        self.inventory_tree = ttk.Treeview(self.tab_inventory, columns=columns, show="headings")
        for col in columns:
            self.inventory_tree.heading(col, text=col)
        self.inventory_tree.pack(fill="both", expand=True, pady=10)

    def load_farmer_ids(self):
        data = self.execute_query("SELECT id,name FROM farmers ORDER BY name", fetch=True)
        if data:
            values = [f"{row[0]} - {row[1]}" for row in data]
            self.inv_farmer_id["values"] = values
        else:
            self.inv_farmer_id["values"] = []

    def load_inventory(self):
        if not hasattr(self, "inventory_tree"):
            return

        for item in self.inventory_tree.get_children():
            self.inventory_tree.delete(item)

        farmer_id = getattr(self, "farmer_id", None)
        if farmer_id:
            query = """
                SELECT i.id, i.product_name, i.quantity, i.harvest_date, i.farmer_id, f.name
                FROM inventory i
                LEFT JOIN farmers f ON i.farmer_id = f.id
                WHERE i.farmer_id = %s
                ORDER BY i.created_at DESC
            """
            data = self.execute_query(query, (farmer_id,), fetch=True)
        else:
            query = """
                SELECT i.id, i.product_name, i.quantity, i.harvest_date, i.farmer_id, f.name
                FROM inventory i
                LEFT JOIN farmers f ON i.farmer_id = f.id
                ORDER BY i.created_at DESC
            """
            data = self.execute_query(query, fetch=True)

        if data:
            for row in data:
                self.inventory_tree.insert("", "end", values=row)

    def add_inventory(self):
        name = self.inv_name.get().strip()
        qty = self.inv_qty.get().strip()
        date = self.inv_date.get().strip()
        farmer_text = self.inv_farmer_id.get().strip()
        farmer_id = getattr(self, "farmer_id", None)

        if not name or not qty or not date:
            messagebox.showerror("Error", "All fields are required")
            return
        if not qty.isdigit():
            messagebox.showerror("Error", "Quantity must be a number")
            return
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Date must be in YYYY-MM-DD format")
            return

        if farmer_id is None:
            if farmer_text:
                try:
                    farmer_id = int(farmer_text.split(" - ")[0])
                except Exception:
                    farmer_id = None

        self.execute_query(
            "INSERT INTO inventory (product_name, quantity, harvest_date, farmer_id) VALUES (%s,%s,%s,%s)",
            (name, int(qty), date, farmer_id),
        )

        self.inv_name.delete(0, tk.END)
        self.inv_qty.delete(0, tk.END)
        self.inv_date.delete(0, tk.END)
        self.load_inventory()
        self.update_dashboard()

    def create_orders_tab(self):
        frame = ttk.Frame(self.tab_orders)
        frame.pack(pady=10, fill="x")

        ttk.Label(frame, text="Customer Name").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.order_customer = ttk.Entry(frame, width=20)
        self.order_customer.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Product").grid(row=0, column=2, padx=5, pady=5, sticky="e")
        self.order_product = ttk.Combobox(frame, width=20, state="readonly")
        self.order_product.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame, text="Quantity").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.order_qty = ttk.Entry(frame, width=10)
        self.order_qty.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Destination").grid(row=1, column=2, padx=5, pady=5, sticky="e")
        self.order_dest = ttk.Entry(frame, width=20)
        self.order_dest.grid(row=1, column=3, padx=5, pady=5)

        self.place_order_btn = ttk.Button(frame, text="Place Order", command=self.place_order)
        self.place_order_btn.grid(row=2, column=0, padx=5, pady=10)
        ttk.Button(frame, text="Refresh", command=self.load_orders).grid(row=2, column=1, padx=5, pady=10)

        status_frame = ttk.Frame(self.tab_orders)
        status_frame.pack(pady=5)
        ttk.Button(
            status_frame,
            text="Mark as Shipped",
            command=lambda: self.update_order_status("Shipped"),
        ).grid(row=0, column=0, padx=5)
        ttk.Button(
            status_frame,
            text="Mark as Delivered",
            command=lambda: self.update_order_status("Delivered"),
        ).grid(row=0, column=1, padx=5)

        columns = ("id", "customer", "product", "qty", "destination", "status")
        self.orders_tree = ttk.Treeview(self.tab_orders, columns=columns, show="headings")
        for col in columns:
            self.orders_tree.heading(col, text=col)
        self.orders_tree.pack(fill="both", expand=True, pady=10)

        self.load_product_names()

    def load_product_names(self):
        farmer_id = getattr(self, "farmer_id", None)
        if farmer_id:
            data = self.execute_query(
                "SELECT DISTINCT product_name FROM inventory WHERE quantity > 0 AND farmer_id=%s",
                (farmer_id,),
                fetch=True,
            )
        else:
            data = self.execute_query(
                "SELECT DISTINCT product_name FROM inventory WHERE quantity > 0",
                fetch=True,
            )
        if data:
            products = [row[0] for row in data]
            if products:
                self.order_product["values"] = products
                try:
                    self.place_order_btn.state(["!disabled"])
                except Exception:
                    pass
            else:
                # No products available
                self.order_product["values"] = ["No products available"]
                try:
                    self.place_order_btn.state(["disabled"])
                except Exception:
                    pass
        else:
            self.order_product["values"] = ["No products available"]
            try:
                self.place_order_btn.state(["disabled"])
            except Exception:
                pass

    def load_orders(self):
        if not hasattr(self, "orders_tree"):
            return
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)

        farmer_id = getattr(self, "farmer_id", None)
        if farmer_id:
            data = self.execute_query(
                """
                SELECT id, customer_name, product_name, quantity, destination, status
                FROM orders
                WHERE supplier_farmer_id=%s
                ORDER BY created_at DESC
                """,
                (farmer_id,),
                fetch=True,
            )
        else:
            data = self.execute_query(
                """
                SELECT id, customer_name, product_name, quantity, destination, status
                FROM orders
                ORDER BY created_at DESC
                """,
                fetch=True,
            )
        if data:
            for row in data:
                self.orders_tree.insert("", "end", values=row)
        self.update_dashboard()

    def place_order(self):
        customer = self.order_customer.get().strip()
        product = self.order_product.get().strip()
        qty = self.order_qty.get().strip()
        dest = self.order_dest.get().strip()

        if not all([customer, product, qty, dest]):
            messagebox.showerror("Error", "All fields are required")
            return
        if not qty.isdigit():
            messagebox.showerror("Error", "Quantity must be a number")
            return
        qty = int(qty)

        supplier_farmer_id = getattr(self, "farmer_id", None)
        if not supplier_farmer_id:
            messagebox.showerror("Error", "Only farmers can place orders linked to inventory")
            return

        available = self.execute_query(
            "SELECT SUM(quantity) FROM inventory WHERE product_name=%s AND farmer_id=%s",
            (product, supplier_farmer_id),
            fetch=True,
        )
        total_available = available[0][0] if available and available[0][0] else 0
        if qty > total_available:
            messagebox.showerror("Error", f"Not enough {product} available in your inventory")
            return

        self.execute_query(
            """
            INSERT INTO orders (customer_name, product_name, quantity, destination, supplier_farmer_id)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (customer, product, qty, dest, supplier_farmer_id),
        )

        remaining = qty
        rows = self.execute_query(
            """
            SELECT id, quantity FROM inventory
            WHERE product_name=%s AND farmer_id=%s
            ORDER BY id ASC
            """,
            (product, supplier_farmer_id),
            fetch=True,
        )
        for inv_id, inv_qty in rows:
            if remaining <= 0:
                break
            if inv_qty <= remaining:
                self.execute_query("DELETE FROM inventory WHERE id=%s", (inv_id,))
                remaining -= inv_qty
            else:
                new_qty = inv_qty - remaining
                self.execute_query("UPDATE inventory SET quantity=%s WHERE id=%s", (new_qty, inv_id))
                remaining = 0

        self.order_customer.delete(0, tk.END)
        self.order_product.set("")
        self.order_qty.delete(0, tk.END)
        self.order_dest.delete(0, tk.END)

        self.load_orders()
        self.load_product_names()
        self.load_inventory()
        self.update_dashboard()
        messagebox.showinfo("Success", "Order placed successfully")

    def update_order_status(self, new_status):
        selected = self.orders_tree.selection()
        if not selected:
            messagebox.showerror("Error", "Select an order")
            return
        order_id = self.orders_tree.item(selected[0])["values"][0]
        self.execute_query("UPDATE orders SET status=%s WHERE id=%s", (new_status, order_id))
        self.load_orders()

    def create_logistics_tab(self):
        header = ttk.Label(self.tab_logistics, text="Logistics Planner", font=("Arial", 16))
        header.pack(pady=10)

        frame = ttk.Frame(self.tab_logistics)
        frame.pack(pady=10, fill="x")

        ttk.Label(frame, text="Order").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.log_order = ttk.Combobox(frame, width=40, state="readonly")
        self.log_order.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Transport").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.log_transport = ttk.Combobox(frame, width=20, state="readonly", values=["Truck", "Van", "Drone"])
        self.log_transport.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(frame, text="Distance (km)").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.log_distance = ttk.Entry(frame, width=10)
        self.log_distance.grid(row=2, column=1, padx=5, pady=5)

        ttk.Button(frame, text="Calculate", command=self.calculate_logistics).grid(
            row=3, column=0, padx=5, pady=10
        )
        ttk.Button(frame, text="Save Plan", command=self.save_logistics_plan).grid(
            row=3, column=1, padx=5, pady=10
        )
        ttk.Button(frame, text="Load Orders", command=self.load_logistics_orders).grid(
            row=3, column=2, padx=5, pady=10
        )

        self.log_result = ttk.Label(self.tab_logistics, text="", font=("Arial", 12))
        self.log_result.pack(pady=10)

        self.load_logistics_orders()

    def load_logistics_orders(self):
        farmer_id = getattr(self, "farmer_id", None)
        if farmer_id:
            data = self.execute_query(
                """
                SELECT id, customer_name, product_name
                FROM orders
                WHERE status='Pending' AND supplier_farmer_id=%s
                ORDER BY created_at DESC
                """,
                (farmer_id,),
                fetch=True,
            )
        else:
            data = self.execute_query(
                """
                SELECT id, customer_name, product_name
                FROM orders
                WHERE status='Pending'
                ORDER BY created_at DESC
                """,
                fetch=True,
            )

        if data:
            values = [f"{row[0]} - {row[1]} ({row[2]})" for row in data]
            self.log_order["values"] = values
        else:
            self.log_order["values"] = []

    def calculate_logistics(self):
        order_text = self.log_order.get().strip()
        transport = self.log_transport.get().strip()
        distance_text = self.log_distance.get().strip()
        if not order_text or not transport or not distance_text:
            messagebox.showerror("Error", "Select order, transport and enter distance")
            return
        try:
            distance = float(distance_text)
        except ValueError:
            messagebox.showerror("Error", "Distance must be a number")
            return

        try:
            order_id = int(order_text.split(" - ")[0])
        except Exception:
            order_id = None

        dest_place = ""
        if order_id is not None:
            row = self.execute_query("SELECT destination FROM orders WHERE id=%s", (order_id,), fetch=True)
            if row:
                dest_place = row[0][0]

        cost_per_km = {"Truck": 1.5, "Van": 2.0, "Drone": 0.5}
        speed_kmh = {"Truck": 60, "Van": 70, "Drone": 40}

        cost = distance * cost_per_km[transport]
        time_h = distance / speed_kmh[transport]

        symbol = get_currency_symbol_from_location(dest_place)
        self.log_result.config(text=f"Cost: {symbol}{cost:.2f} | Time: {time_h:.1f} hours")

    def save_logistics_plan(self):
        order_text = self.log_order.get().strip()
        transport = self.log_transport.get().strip()
        distance_text = self.log_distance.get().strip()
        if not order_text or not transport or not distance_text:
            messagebox.showerror("Error", "Fill all logistics fields")
            return
        try:
            distance = float(distance_text)
        except ValueError:
            messagebox.showerror("Error", "Distance must be a number")
            return
        try:
            order_id = int(order_text.split(" - ")[0])
        except Exception:
            messagebox.showerror("Error", "Invalid order selection")
            return

        cost_per_km = {"Truck": 1.5, "Van": 2.0, "Drone": 0.5}
        speed_kmh = {"Truck": 60, "Van": 70, "Drone": 40}

        cost = distance * cost_per_km[transport]
        time_h = distance / speed_kmh[transport]

        self.execute_query(
            """
            INSERT INTO logistics (order_id, transport_method, distance_km, estimated_cost, estimated_time_hours)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (order_id, transport, distance, cost, time_h),
        )
        messagebox.showinfo("Success", "Logistics plan saved")

    def create_farmers_tab(self):
        header = ttk.Label(self.tab_farmers, text="Farmers", font=("Arial", 16))
        header.pack(pady=10)

        columns = ("id", "name", "contact", "email", "location", "latitude", "longitude", "username", "language")
        self.farmers_tree = ttk.Treeview(self.tab_farmers, columns=columns, show="headings")
        for col in columns:
            self.farmers_tree.heading(col, text=col)
        self.farmers_tree.pack(fill="both", expand=True, pady=10)

        btn_frame = ttk.Frame(self.tab_farmers)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Refresh", command=self.load_farmers).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="View on Map", command=self.view_farmer_on_map).grid(row=0, column=1, padx=5)

    def load_farmers(self):
        if not hasattr(self, "farmers_tree"):
            return
        for item in self.farmers_tree.get_children():
            self.farmers_tree.delete(item)

        data = self.execute_query(
            """
            SELECT id, name, contact, email, location, latitude, longitude, username, language
            FROM farmers
            ORDER BY created_at DESC
            """,
            fetch=True,
        )
        if data:
            for row in data:
                self.farmers_tree.insert("", "end", values=row)

    def view_farmer_on_map(self):
        selected = self.farmers_tree.selection()
        if not selected:
            messagebox.showerror("Error", "Select a farmer")
            return
        values = self.farmers_tree.item(selected[0])["values"]
        lat = values[5]
        lon = values[6]
        if lat is None or lon is None:
            messagebox.showerror("Error", "Farmer has no coordinates")
            return
        url = f"https://www.google.com/maps?q={lat},{lon}"
        webbrowser.open(url)

    def create_tracking_tab(self):
        header = ttk.Label(self.tab_tracking, text="Vehicle Tracking", font=("Arial", 16))
        header.pack(pady=10)

        frame = ttk.Frame(self.tab_tracking)
        frame.pack(pady=5, fill="x")

        ttk.Label(frame, text="Vehicle").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.track_vehicle = ttk.Combobox(frame, width=30, state="readonly")
        self.track_vehicle.grid(row=0, column=1, padx=5, pady=5)

        ttk.Button(frame, text="Track on Map", command=self.track_vehicle_on_map).grid(
            row=0, column=2, padx=5, pady=5
        )
        ttk.Button(frame, text="Simulate Movement", command=self.simulate_movement).grid(
            row=0, column=3, padx=5, pady=5
        )
        ttk.Button(frame, text="Refresh", command=self.load_vehicles).grid(row=0, column=4, padx=5, pady=5)

        columns = ("id", "name", "type", "latitude", "longitude", "status", "last_update")
        self.vehicles_tree = ttk.Treeview(self.tab_tracking, columns=columns, show="headings")
        for col in columns:
            self.vehicles_tree.heading(col, text=col)
        self.vehicles_tree.pack(fill="both", expand=True, pady=10)

    def load_vehicles(self):
        if not hasattr(self, "vehicles_tree"):
            return
        for item in self.vehicles_tree.get_children():
            self.vehicles_tree.delete(item)

        data = self.execute_query(
            """
            SELECT id, name, type, current_latitude, current_longitude, status, last_update
            FROM vehicles
            ORDER BY name
            """,
            fetch=True,
        )
        if data:
            for row in data:
                self.vehicles_tree.insert("", "end", values=row)
            names = [f"{row[0]} - {row[1]}" for row in data]
            self.track_vehicle["values"] = names
        else:
            self.track_vehicle["values"] = []

    def track_vehicle_on_map(self):
        vehicle_text = self.track_vehicle.get().strip()
        if not vehicle_text:
            messagebox.showerror("Error", "Select a vehicle")
            return
        try:
            vehicle_id = int(vehicle_text.split(" - ")[0])
        except Exception:
            messagebox.showerror("Error", "Invalid vehicle selection")
            return

        data = self.execute_query(
            "SELECT current_latitude,current_longitude FROM vehicles WHERE id=%s",
            (vehicle_id,),
            fetch=True,
        )
        if data and data[0][0] is not None and data[0][1] is not None:
            lat, lon = data[0]
            url = f"https://www.google.com/maps?q={lat},{lon}"
            webbrowser.open(url)
        else:
            messagebox.showerror("Error", "Vehicle has no coordinates")

    def simulate_movement(self):
        data = self.execute_query("SELECT id,current_latitude,current_longitude FROM vehicles", fetch=True)
        if not data:
            return
        for row in data:
            vid, lat, lon = row
            if lat is None or lon is None:
                continue
            new_lat = float(lat) + random.uniform(-0.05, 0.05)
            new_lon = float(lon) + random.uniform(-0.05, 0.05)
            self.execute_query(
                """
                UPDATE vehicles
                SET current_latitude=%s, current_longitude=%s, last_update=NOW()
                WHERE id=%s
                """,
                (new_lat, new_lon, vid),
            )
        self.load_vehicles()
        messagebox.showinfo("Simulation", "Vehicle positions updated")

class FarmerDashboard(FarmSupplyApp):
    def __init__(self, root, login_system, username):
        self.login_system = login_system
        self.username = username
        self.farmer_id = None
        self.farmer_name = None
        self.root = root
        self.db_connection = get_db_connection()
        self.get_farmer_info()
        super().__init__(root)
        self.customize_for_farmer()

    def get_farmer_info(self):
        if not self.db_connection:
            return
        cursor = self.db_connection.cursor()
        cursor.execute("SELECT id,name FROM farmers WHERE username=%s", (self.username,))
        row = cursor.fetchone()
        if row:
            self.farmer_id, self.farmer_name = row
        cursor.close()

    def customize_for_farmer(self):
        top = tk.Frame(self.root, bg="#2E8B57", height=50)
        top.pack(fill="x")
        label = tk.Label(
            top,
            text=f"Welcome, {self.farmer_name}",
            bg="#2E8B57",
            fg="white",
            font=("Arial", 14, "bold"),
        )
        label.pack(side="left", padx=10)

        btn = tk.Button(top, text="Logout", bg="#FF9800", fg="white", command=self.logout)
        btn.pack(side="right", padx=10)

        try:
            idx = self.tab_control.index(self.tab_farmers)
            self.tab_control.forget(idx)
        except Exception:
            pass

        if hasattr(self, "inv_farmer_id"):
            self.inv_farmer_id.set("Your Farm")
            self.inv_farmer_id.config(state="disabled")

        self.load_inventory()
        self.load_orders()
        self.load_logistics_orders()
        self.load_vehicles()
        self.update_dashboard()

    def logout(self):
        self.root.destroy()
        self.login_system.root.deiconify()

class SignupWindow:
    def __init__(self, parent, login_system):
        self.login_system = login_system
        self.win = tk.Toplevel(parent)
        self.win.title("Farmer Registration")
        self.win.geometry("480x700")
        try:
            self.win.resizable(True, True)
            self.win.minsize(420, 380)
            self.win.grab_set()
            self.win.lift()
            self.win.focus_force()
            self.win.attributes("-topmost", True)
            self.win.after(500, lambda: self.win.attributes("-topmost", False))
        except Exception:
            pass

        header = tk.Label(self.win, text="Farmer Registration", font=("Arial", 16, "bold"))
        header.pack(pady=10)

        outer = tk.Frame(self.win)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas)

        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        def _on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _on_configure)

        self.fields = {}
        labels = ["Full Name", "Contact", "Email"]
        for label in labels:
            tk.Label(inner, text=label).pack(pady=5, anchor="w", padx=10)
            entry = tk.Entry(inner)
            entry.pack(pady=5, padx=10, fill="x")
            key = label.lower().replace(" ", "_")
            self.fields[key] = entry

        tk.Label(inner, text="Location").pack(pady=5, anchor="w", padx=10)
        loc_frame = tk.Frame(inner)
        loc_frame.pack(pady=5, padx=10, fill="x")
        self.location_entry = tk.Entry(loc_frame, width=30)
        self.location_entry.pack(side="left", padx=5, fill="x", expand=True)
        tk.Button(loc_frame, text="Search", command=self.search_location_suggestions).pack(side="left")

        self.suggestion_listbox = tk.Listbox(inner, height=5)
        self.suggestion_listbox.pack(pady=5, fill="x", padx=10)
        self.suggestion_listbox.bind("<<ListboxSelect>>", self.select_location_suggestion)

        tk.Label(inner, text="Preferred Language").pack(pady=5, anchor="w", padx=10)
        self.language_var = tk.StringVar(value="English")
        self.language_combo = ttk.Combobox(
            inner,
            textvariable=self.language_var,
            state="readonly",
            values=["English", "Tamil", "Hindi", "Telugu", "Kannada", "Malayalam"],
        )
        self.language_combo.pack(pady=5, padx=10, fill="x")

        tk.Label(inner, text="Username").pack(pady=5, anchor="w", padx=10)
        self.username_entry = tk.Entry(inner)
        self.username_entry.pack(pady=5, padx=10, fill="x")

        tk.Label(inner, text="Password").pack(pady=5, anchor="w", padx=10)
        self.password_entry = tk.Entry(inner, show="*")
        self.password_entry.pack(pady=5, padx=10, fill="x")

        tk.Label(inner, text="Confirm Password").pack(pady=5, anchor="w", padx=10)
        self.confirm_password_entry = tk.Entry(inner, show="*")
        self.confirm_password_entry.pack(pady=5, padx=10, fill="x")

        
        bottom_frame = tk.Frame(self.win)
        bottom_frame.pack(side="bottom", fill="x")
        self.register_btn = tk.Button(
            bottom_frame,
            text="Register",
            command=self.register,
            bg="#2E8B57",
            fg="white",
            font=("Arial", 11, "bold"),
        )
        self.register_btn.pack(pady=10)

    def search_location_suggestions(self):
        query = self.location_entry.get().strip()
        suggestions = get_location_suggestions(query)
        self.suggestion_listbox.delete(0, tk.END)
        for s in suggestions:
            self.suggestion_listbox.insert(tk.END, s)

    def select_location_suggestion(self, event):
        if not self.suggestion_listbox.curselection():
            return
        index = self.suggestion_listbox.curselection()[0]
        value = self.suggestion_listbox.get(index)
        self.location_entry.delete(0, tk.END)
        self.location_entry.insert(0, value)
        self.suggestion_listbox.delete(0, tk.END)

    def register(self):
        name = self.fields["full_name"].get().strip()
        contact = self.fields["contact"].get().strip()
        email = self.fields["email"].get().strip()
        location = self.location_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        confirm_password = self.confirm_password_entry.get().strip()
        language = self.language_var.get().strip()

        try:
            logging.info("Register attempt: name=%s contact=%s email=%s location=%s username=%s language=%s pass_len=%d",
                         name, contact, email, location, username, language, len(password))
        except Exception:
            pass

        if not all([name, contact, email, location, username, password]):
            messagebox.showerror("Error", "All fields are required")
            return
        if password != confirm_password:
            messagebox.showerror("Error", "Passwords do not match")
            return
        if len(password) < 6:
            messagebox.showerror("Error", "Password must be at least 6 characters")
            return

        conn = get_db_connection()
        if not conn:
            return

        cursor = None
        success = False
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM farmers WHERE username=%s", (username,))
            if cursor.fetchone():
                logging.info("Username already exists: %s", username)
                messagebox.showerror("Error", "Username already exists")
                return

            lat, lon = get_coordinates(location)
            hashed = hashlib.sha256(password.encode()).hexdigest()
            cursor.execute(
                """
                INSERT INTO farmers (name, contact, email, location, latitude, longitude, username, password, language)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (name, contact, email, location, lat, lon, username, hashed, language),
            )
            conn.commit()
            success = True
            logging.info("Registration successful for username=%s", username)
        except mysql.connector.IntegrityError as ie:
            logging.exception("IntegrityError during registration for username=%s", username)
            try:
                print(f"Database Integrity Error: {ie}", file=sys.stderr)
            except Exception:
                pass
            messagebox.showerror("Database Error", f"Integrity error: {ie}")
        except Exception as e:
            logging.exception("Failed to register user %s", username)
            try:
                print(f"Failed to register: {e}", file=sys.stderr)
            except Exception:
                pass
            messagebox.showerror("Database Error", f"Failed to register: {e}")
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            try:
                conn.close()
            except Exception:
                pass

        if success:
            messagebox.showinfo("Success", "Registration successful")
            self.win.destroy()

class ForgotPasswordWindow:
    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.title("Forgot Password")
        self.win.geometry("350x350")
        self.generated_otp = None

        tk.Label(self.win, text="Reset Password (Farmer)", font=("Arial", 14, "bold")).pack(pady=10)

        tk.Label(self.win, text="Username").pack(pady=5)
        self.username_entry = tk.Entry(self.win)
        self.username_entry.pack(pady=5)

        tk.Label(self.win, text="Contact").pack(pady=5)
        self.contact_entry = tk.Entry(self.win)
        self.contact_entry.pack(pady=5)

        tk.Button(self.win, text="Send OTP", command=self.send_otp).pack(pady=10)

        tk.Label(self.win, text="Enter OTP").pack(pady=5)
        self.otp_entry = tk.Entry(self.win)
        self.otp_entry.pack(pady=5)

        tk.Label(self.win, text="New Password").pack(pady=5)
        self.new_password_entry = tk.Entry(self.win, show="*")
        self.new_password_entry.pack(pady=5)

        tk.Label(self.win, text="Confirm Password").pack(pady=5)
        self.confirm_new_password_entry = tk.Entry(self.win, show="*")
        self.confirm_new_password_entry.pack(pady=5)

        tk.Button(self.win, text="Reset Password", command=self.reset_password).pack(pady=10)

    def send_otp(self):
        username = self.username_entry.get().strip()
        contact = self.contact_entry.get().strip()
        if not username or not contact:
            messagebox.showerror("Error", "Enter username and contact")
            return

        conn = get_db_connection()
        if not conn:
            return
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM farmers WHERE username=%s AND contact=%s", (username, contact))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            messagebox.showerror("Error", "No farmer found with given username and contact")
            return

        otp = random.randint(100000, 999999)
        self.generated_otp = str(otp)
        messagebox.showinfo("OTP Sent", f"Your OTP is: {otp}\n(For demo purposes, shown here.)")

    def reset_password(self):
        if not self.generated_otp:
            messagebox.showerror("Error", "Please request OTP first")
            return
        entered_otp = self.otp_entry.get().strip()
        if entered_otp != self.generated_otp:
            messagebox.showerror("Error", "Invalid OTP")
            return

        new_pass = self.new_password_entry.get().strip()
        confirm_pass = self.confirm_new_password_entry.get().strip()
        if not new_pass or not confirm_pass:
            messagebox.showerror("Error", "Enter new password and confirm")
            return
        if new_pass != confirm_pass:
            messagebox.showerror("Error", "Passwords do not match")
            return
        if len(new_pass) < 6:
            messagebox.showerror("Error", "Password must be at least 6 characters")
            return

        username = self.username_entry.get().strip()
        contact = self.contact_entry.get().strip()

        conn = get_db_connection()
        if not conn:
            return
        cursor = conn.cursor()
        hashed = hashlib.sha256(new_pass.encode()).hexdigest()
        cursor.execute(
            "UPDATE farmers SET password=%s WHERE username=%s AND contact=%s",
            (hashed, username, contact),
        )
        conn.commit()
        cursor.close()
        conn.close()
        messagebox.showinfo("Success", "Password reset successful")
        self.win.destroy()

class AdminDashboard:
    def __init__(self, root, login_system):
        self.root = root
        self.login_system = login_system
        self.root.title("Admin Dashboard")
        self.root.geometry("900x500")

        tk.Label(root, text="Admin Dashboard", font=("Arial", 18, "bold")).pack(pady=10)

        columns = ("id", "name", "contact", "email", "location", "username", "language", "created_at")
        self.tree = ttk.Treeview(root, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.pack(fill="both", expand=True, pady=10)

        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Refresh", command=self.load).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="Logout", command=self.logout).grid(row=0, column=1, padx=5)

        self.load()

    def load(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        conn = get_db_connection()
        if not conn:
            return
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, name, contact, email, location, username, language, created_at
            FROM farmers
            ORDER BY created_at DESC
            """
        )
        rows = cursor.fetchall()
        for r in rows:
            self.tree.insert("", "end", values=r)
        cursor.close()
        conn.close()

    def logout(self):
        self.root.destroy()
        self.login_system.root.deiconify()

class LoginSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Farm Supply Chain - Login")
        self.root.geometry("500x450")
        self.root.configure(bg="#3CB371")

        title_frame = tk.Frame(root, bg="#3CB371")
        title_frame.pack(pady=10)
        tk.Label(
            title_frame,
            text="🌾  SMART FARM SUPPLY CHAIN  🌾",
            font=("Arial", 20, "bold"),
            bg="#3CB371",
            fg="white",
        ).pack()

        lang_frame = tk.Frame(root, bg="#3CB371")
        lang_frame.pack(pady=2)
        tk.Label(
            lang_frame,
            text="Language:",
            bg="#3CB371",
            fg="white",
            font=("Arial", 11, "bold"),
        ).pack(side="left", padx=5)
        self.ui_language_var = tk.StringVar(value="English")
        lang_combo = ttk.Combobox(
            lang_frame,
            textvariable=self.ui_language_var,
            state="readonly",
            width=12,
            values=["English", "Tamil", "Hindi", "Telugu", "Kannada", "Malayalam"],
        )
        lang_combo.pack(side="left")

        container = tk.Frame(root, bg="white", bd=2, relief="ridge")
        container.place(relx=0.5, rely=0.55, anchor="center", width=360, height=320)

        tk.Label(container, text="Username", font=("Arial", 12, "bold"), bg="white").pack(pady=5)
        self.u = tk.Entry(container, font=("Arial", 12), bd=1, relief="solid")
        self.u.pack(pady=5, ipadx=5, ipady=3)

        tk.Label(container, text="Password", font=("Arial", 12, "bold"), bg="white").pack(pady=5)
        self.p = tk.Entry(container, show="*", font=("Arial", 12), bd=1, relief="solid")
        self.p.pack(pady=5, ipadx=5, ipady=3)

        self.show_pw_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            container,
            text="Show Password",
            variable=self.show_pw_var,
            bg="white",
            command=self.toggle_password,
        ).pack(pady=2)

        self.type = tk.StringVar(value="farmer")
        tk.Radiobutton(container, text="Farmer Login", variable=self.type, value="farmer", bg="white").pack()
        tk.Radiobutton(container, text="Admin Login", variable=self.type, value="admin", bg="white").pack()

        tk.Button(
            container,
            text="LOGIN",
            command=self.login,
            bg="#2E8B57",
            fg="white",
            font=("Arial", 12, "bold"),
            width=15,
        ).pack(pady=8)
        tk.Button(
            container,
            text="New Farmer? Sign Up",
            command=self.signup,
            bg="#FF9800",
            fg="white",
            font=("Arial", 11, "bold"),
            width=20,
        ).pack(pady=3)
        tk.Button(
            container,
            text="Forgot Password?",
            command=self.open_forgot_password,
            bg="#2196F3",
            fg="white",
            font=("Arial", 10, "bold"),
            width=20,
        ).pack(pady=3)

    def toggle_password(self):
        if self.show_pw_var.get():
            self.p.config(show="")
        else:
            self.p.config(show="*")

    def login(self):
        username = self.u.get().strip()
        password = self.p.get().strip()
        if not username or not password:
            messagebox.showerror("Error", "Enter username and password")
            return

        if self.type.get() == "admin":
            if username == "sabari" and password == "sabari@123":
                self.open_admin()
                return
            messagebox.showerror("Error", "Invalid admin credentials")
            return

        conn = get_db_connection()
        if not conn:
            return
        cursor = conn.cursor()
        hashed = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute("SELECT id FROM farmers WHERE username=%s AND password=%s", (username, hashed))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:
            self.open_farmer(username)
        else:
            messagebox.showerror("Error", "Invalid farmer credentials")

    def signup(self):
        return SignupWindow(self.root, self)

    def open_forgot_password(self):
        ForgotPasswordWindow(self.root)

    def open_admin(self):
        self.root.withdraw()
        win = tk.Toplevel()
        AdminDashboard(win, self)

    def open_farmer(self, username):
        self.root.withdraw()
        win = tk.Toplevel()
        FarmerDashboard(win, self, username)

if __name__ == "__main__":
    root = tk.Tk()
    LoginSystem(root)
    root.mainloop()
