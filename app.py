from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import AzureOpenAI
import os
from dotenv import dotenv_values
import pyodbc
from datetime import datetime

# Load environment variables from .env file
load_dotenv(override=True)

# Get configurations from environment variables
azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
azure_openai_chat_completions_deployment_name = os.getenv("AZURE_OPENAI_CHAT_COMPLETIONS_DEPLOYMENT_NAME")

azure_openai_embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL")
embedding_vector_dimensions = os.getenv("EMBEDDING_VECTOR_DIMENSIONS")

azure_search_service_endpoint = os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT")
azure_search_service_admin_key = os.getenv("AZURE_SEARCH_SERVICE_ADMIN_KEY")
search_index_name = os.getenv("SEARCH_INDEX_NAME")

# Database configuration
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize the OpenAI client
openai_client = AzureOpenAI(
    azure_endpoint=azure_openai_endpoint,
    api_key=azure_openai_api_key,
    api_version="2024-06-01"
)

def get_db_connection():
    """Create and return a database connection."""
    return pyodbc.connect(DB_CONNECTION_STRING)

@app.route('/affirm', methods=['GET'])
def get_affirmations():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Assuming the affirmations table has columns: id, text, category (or whatever columns you have)
            query = 'SELECT TOP 1 * FROM affirmations ORDER BY NEWID();'
            cursor.execute(query)
            
            # Fetch all rows and convert to list of dictionaries
            columns = [column[0] for column in cursor.description]
            affirmations = []
            for row in cursor.fetchall():
                affirmation = dict(zip(columns, row))
                affirmations.append(affirmation)

            return jsonify({'affirmations': affirmations})

    except Exception as e:
        print(f"Database error: {str(e)}")
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@app.route('/chat', methods=['POST'])
def chat():
    try:
        # Get the chat message from the JSON body
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400
            
        chat_message = data.get('message')
        
        messages = [
            {
                "role": "system",
                "content": "You are a compassionate assistant providing guidance and support for someone struggling with feelings of worthlessness and mental health challenges."
            },
            {
                "role": "user",
                "content": chat_message
            }
        ]

        response = openai_client.chat.completions.create(
            model=azure_openai_chat_completions_deployment_name,
            messages=messages,
            extra_body={
                "data_sources": [
                    {
                        "type": "azure_search",
                        "parameters": {
                            "endpoint": azure_search_service_endpoint,
                            "index_name": search_index_name,
                            "authentication": {
                                "type": "api_key",
                                "key": azure_search_service_admin_key,
                            }
                        }
                    }
                ]
            }
        )
        
        print(response.choices[0])

        if hasattr(response, 'choices') and len(response.choices) > 0:
            response_message = response.choices[0].message.content
        else:
            response_message = "No response received."

        return jsonify({'response': response_message})
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
    
    
@app.route('/get_user_info', methods=['POST'])
def get_user_info():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    try:
        conn = pyodbc.connect(DB_CONNECTION_STRING)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT daily_score, sleep, water, steps, mood, pfp, first_name, last_name, email, phone_number, emergency_contact_name, relation, emergency_contact_phone
            FROM userInfo
            WHERE email = ? AND password = ?
        """, (email, password))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            user_info = {
                "daily_score": row[0],
                "sleep": row[1],
                "water": row[2],
                "steps": row[3],
                "mood": row[4],
                "pfp": row[5],
                "first_name": row[6],
                "last_name": row[7],
                "email": row[8],
                "phone_number": row[9],
                "emergency_contact_name": row[10],
                "relation": row[11],
                "emergency_contact_phone": row[12]
            }
            return jsonify(user_info), 200
        else:
            return jsonify({"error": "Invalid email or password"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/sign_up', methods=['POST'])
def sign_up():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400

    try:
        conn = pyodbc.connect(DB_CONNECTION_STRING)
        cursor = conn.cursor()
        
        # Check if email already exists
        cursor.execute("SELECT email FROM userInfo WHERE email = ?", (email,))
        row = cursor.fetchone()
        
        if row:
            conn.close()
            return jsonify({"error": "Email already exists"}), 409
        
        # Insert new user
        cursor.execute("""
            INSERT INTO userInfo (name, email, password)
            VALUES (?, ?, ?)
        """, (name, email, password))
        conn.commit()
        conn.close()

        return jsonify({"message": "User added successfully"}), 201

    except pyodbc.Error as db_err:
        return jsonify({"error": "Database error", "details": str(db_err)}), 500
    except Exception as e:
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500
    
@app.route('/check_user', methods=['POST'])
def check_user():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    try:
        conn = pyodbc.connect(DB_CONNECTION_STRING)
        cursor = conn.cursor()
        
        # Check if email exists
        cursor.execute("SELECT password FROM userInfo WHERE email = ?", (email,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return jsonify({"error": "Email not found"}), 404
        
        # Check if password matches
        stored_password = row[0]
        if stored_password != password:
            conn.close()
            return jsonify({"error": "Incorrect password"}), 401
        
        # Fetch user information if email and password are correct
        cursor.execute("""
            SELECT name, email, phone_number, emergency_contact_name, relation, emergency_contact_phone
            FROM userInfo
            WHERE email = ? AND password = ?
        """, (email, password))
        row = cursor.fetchone()
        conn.close()

        if row:
            user_info = {
                "name": row[0],
                "email": row[1],
                "phone_number": row[2],
                "emergency_contact_name": row[3],
                "relation": row[4],
                "emergency_contact_phone": row[5]
            }
            return jsonify(user_info), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/user_info', methods=['POST'])
def gett_user_info():
    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({"error": "Email is required"}), 400

    try:
        conn = pyodbc.connect(DB_CONNECTION_STRING)
        cursor = conn.cursor()

        # Fetch user and wellness data
        cursor.execute("""
            SELECT name, email, phone_number, emergency_contact_name, relation, emergency_contact_phone, 
                   mood_score, sleep_hours, water_glasses, steps
            FROM userInfo
            WHERE email = ?
        """, (email,))
        row = cursor.fetchone()
        conn.close()

        if row:
            user_info = {
                "name": row[0],
                "email": row[1],
                "phone_number": row[2],
                "emergency_contact_name": row[3],
                "relation": row[4],
                "emergency_contact_phone": row[5],
                "mood_score": row[6],
                "sleep_hours": float(row[7]),
                "water_glasses": row[8],
                "steps": row[9]
            }
            return jsonify(user_info), 200
        else:
            return jsonify({"error": "User not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_wellness', methods=['POST'])
def update_wellness():
    data = request.json
    email = data.get('email')
    updates = data.get('updates', {})

    if not email or not updates:
        return jsonify({"error": "Email and updates are required"}), 400

    try:
        conn = pyodbc.connect(DB_CONNECTION_STRING)
        cursor = conn.cursor()

        # Construct the SQL dynamically
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values()) + [email]

        sql = f"UPDATE userInfo SET {set_clause} WHERE email = ?"
        cursor.execute(sql, values)
        conn.commit()
        conn.close()

        return jsonify({"success": True, "message": "Wellness data updated successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/journal_entries', methods=['GET'])
def get_journal_entries():
    email = request.args.get('email')

    if not email:
        return jsonify({"error": "Email parameter is required"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date, content, activities, score
            FROM JournalEntries
            WHERE email = ?
            ORDER BY date DESC
        """, (email,))
        rows = cursor.fetchall()
        conn.close()

        entries = []
        for row in rows:
            entry = {
                "id": row.id,
                "date": row.date.strftime('%Y-%m-%d %H:%M:%S'),
                "content": row.content,
                "activities": row.activities,
                "score": row.score
            }
            entries.append(entry)

        return jsonify({"entries": entries}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/journal_entries', methods=['POST'])
def create_journal_entry():
    data = request.json
    email = data.get('email')
    content = data.get('content')
    activities = data.get('activities')
    score = data.get('score')
    date = datetime.now()

    if not all([email, content, activities, score]):
        return jsonify({"error": "Email, content, activities, and score are required"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO JournalEntries (email, date, content, activities, score)
            VALUES (?, ?, ?, ?, ?)
        """, (email, date, content, activities, score))
        cursor.execute("SELECT SCOPE_IDENTITY() AS id;")  # For Azure SQL Database
        new_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        return jsonify({"message": "Journal entry created successfully", "id": new_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Make the server accessible from other devices on the network
    app.run(debug=True, host='0.0.0.0', port=5000)
