"""
PostgreSQL Schema Templates for Data Synthesis
------------------------------------------------
Each domain uses its own PostgreSQL schema namespace to avoid table conflicts.
e.g. saas.users, healthcare.patients, fintech.accounts

This is more realistic — real production databases use schema namespacing.
"""

SCHEMAS = [
    {
        "name": "ecommerce",
        "pg_schema": "ecommerce",
        "description": "E-commerce platform with users, products, orders",
        "ddl": """
CREATE SCHEMA IF NOT EXISTS ecommerce;

CREATE TABLE IF NOT EXISTS ecommerce.users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    tier VARCHAR(20) DEFAULT 'standard',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS ecommerce.products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    price NUMERIC(10, 2) NOT NULL,
    stock INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ecommerce.orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES ecommerce.users(id),
    status VARCHAR(20) DEFAULT 'pending',
    total NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    shipped_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS ecommerce.order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES ecommerce.orders(id),
    product_id INTEGER NOT NULL REFERENCES ecommerce.products(id),
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);
""",
        "sample_values": {
            "ecommerce.users.tier": ["standard", "premium", "enterprise"],
            "ecommerce.orders.status": ["pending", "processing", "shipped", "delivered", "cancelled"],
            "ecommerce.products.category": ["electronics", "clothing", "books", "home", "sports"],
        }
    },
    {
        "name": "saas_analytics",
        "pg_schema": "saas",
        "description": "SaaS product analytics with events, sessions, and subscriptions",
        "ddl": """
CREATE SCHEMA IF NOT EXISTS saas;

CREATE TABLE IF NOT EXISTS saas.organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    plan VARCHAR(50) DEFAULT 'free',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    churned_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS saas.users (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES saas.organizations(id),
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(50) DEFAULT 'member',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS saas.events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES saas.users(id),
    org_id INTEGER REFERENCES saas.organizations(id),
    event_name VARCHAR(100) NOT NULL,
    properties JSONB,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS saas.subscriptions (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES saas.organizations(id),
    plan VARCHAR(50) NOT NULL,
    mrr NUMERIC(10, 2) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ended_at TIMESTAMP WITH TIME ZONE
);
""",
        "sample_values": {
            "saas.organizations.plan": ["free", "starter", "pro", "enterprise"],
            "saas.users.role": ["owner", "admin", "member", "viewer"],
            "saas.events.event_name": ["page_view", "button_click", "form_submit", "login", "logout"],
        }
    },
    {
        "name": "healthcare",
        "pg_schema": "healthcare",
        "description": "Healthcare system with patients, appointments, and diagnoses",
        "ddl": """
CREATE SCHEMA IF NOT EXISTS healthcare;

CREATE TABLE IF NOT EXISTS healthcare.patients (
    id SERIAL PRIMARY KEY,
    mrn VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR(10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS healthcare.providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    specialty VARCHAR(100),
    department VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS healthcare.appointments (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES healthcare.patients(id),
    provider_id INTEGER REFERENCES healthcare.providers(id),
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'scheduled',
    appointment_type VARCHAR(50),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS healthcare.diagnoses (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES healthcare.patients(id),
    appointment_id INTEGER REFERENCES healthcare.appointments(id),
    icd_code VARCHAR(20) NOT NULL,
    description TEXT,
    diagnosed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
""",
        "sample_values": {
            "healthcare.appointments.status": ["scheduled", "completed", "cancelled", "no_show"],
            "healthcare.appointments.appointment_type": ["routine", "urgent", "follow_up", "specialist"],
            "healthcare.providers.specialty": ["cardiology", "neurology", "orthopedics", "general"],
        }
    },
    {
        "name": "fintech",
        "pg_schema": "fintech",
        "description": "Financial platform with accounts, transactions, and loans",
        "ddl": """
CREATE SCHEMA IF NOT EXISTS fintech;

CREATE TABLE IF NOT EXISTS fintech.accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    account_type VARCHAR(50) NOT NULL,
    balance NUMERIC(15, 2) DEFAULT 0,
    currency VARCHAR(3) DEFAULT 'USD',
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS fintech.transactions (
    id BIGSERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES fintech.accounts(id),
    amount NUMERIC(15, 2) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    category VARCHAR(100),
    description TEXT,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    balance_after NUMERIC(15, 2)
);

CREATE TABLE IF NOT EXISTS fintech.loans (
    id SERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES fintech.accounts(id),
    principal NUMERIC(15, 2) NOT NULL,
    interest_rate NUMERIC(5, 4) NOT NULL,
    term_months INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    disbursed_at TIMESTAMP WITH TIME ZONE,
    due_date DATE
);
""",
        "sample_values": {
            "fintech.accounts.account_type": ["checking", "savings", "investment", "credit"],
            "fintech.transactions.transaction_type": ["debit", "credit", "transfer", "fee", "interest"],
            "fintech.transactions.category": ["food", "transport", "utilities", "entertainment", "salary"],
            "fintech.loans.status": ["pending", "active", "paid_off", "defaulted"],
        }
    },
    {
        "name": "hr_system",
        "pg_schema": "hr",
        "description": "HR management with employees, departments, and performance reviews",
        "ddl": """
CREATE SCHEMA IF NOT EXISTS hr;

CREATE TABLE IF NOT EXISTS hr.departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    manager_id INTEGER,
    budget NUMERIC(15, 2),
    location VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS hr.employees (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    department_id INTEGER REFERENCES hr.departments(id),
    manager_id INTEGER REFERENCES hr.employees(id),
    title VARCHAR(100),
    salary NUMERIC(12, 2),
    hire_date DATE NOT NULL,
    termination_date DATE
);

CREATE TABLE IF NOT EXISTS hr.performance_reviews (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES hr.employees(id),
    reviewer_id INTEGER REFERENCES hr.employees(id),
    review_period VARCHAR(20),
    rating NUMERIC(3, 1),
    comments TEXT,
    reviewed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hr.time_off_requests (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER REFERENCES hr.employees(id),
    request_type VARCHAR(50),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    approved_by INTEGER REFERENCES hr.employees(id)
);
""",
        "sample_values": {
            "hr.employees.title": ["Engineer", "Senior Engineer", "Manager", "Director", "VP", "Analyst"],
            "hr.time_off_requests.request_type": ["vacation", "sick", "personal", "parental"],
            "hr.time_off_requests.status": ["pending", "approved", "rejected"],
            "hr.performance_reviews.review_period": ["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2024"],
        }
    },
]