from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import re
import shelve
from flask_session import Session
import os

# Configure session
app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'  # Use a strong secret key for sessions
app.config['SESSION_TYPE'] = 'filesystem'  # Store sessions in the file system
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Set max upload to 50 MB (or whatever you need)
Session(app)

# Global variable to store progress
progress = 0

# Set a simple password for entrance
PASSWORD = "1305"

# Helper function to open the shelve data file
def get_processed_equipment_data():
    with shelve.open('equipment_data.db') as db:
        if 'processed_equipment_data' not in db:
            db['processed_equipment_data'] = {}
        data = db['processed_equipment_data']

    # Ensure each equipment entry has all necessary keys
    for equipment_id, details in data.items():
        if 'last_updated' not in details:
            data[equipment_id]['last_updated'] = 'N/A'
    
    return data

    
def save_processed_equipment_data(data):
    with shelve.open('equipment_data.db', writeback=True) as db:
        db['processed_equipment_data'] = data
        # Manually sync to disk to ensure persistence
        db.sync()

def ensure_data_entry(equipment_id):
    data = get_processed_equipment_data()
    if equipment_id not in data:
        data[equipment_id] = {
            'records': [],
            'name': '',
            'operator': '',
            'work_area': '',
            'next_service_hours': '',
            'notes': '',
            'service_interval': '',
            'service_history': [],
            'registration_number': '',
            'last_updated': 'N/A'  # Initialize with 'N/A'
        }
    elif 'last_updated' not in data[equipment_id]:
        # In case 'last_updated' is missing in an existing entry
        data[equipment_id]['last_updated'] = 'N/A'
    save_processed_equipment_data(data)

# Generic processor for .n files that updates names, operators, or work areas based on IDs
def process_n_files(file, detail_type):
    print(f"Processing {detail_type} file...")
    data = get_processed_equipment_data()
    for line in file.stream:
        line = line.decode('utf-8').strip()
        parts = line.split(',')
        if len(parts) >= 2:
            id, value = parts[0].strip('"'), parts[1].strip('"')
            ensure_data_entry(id)
            if detail_type == 'name':
                # Update name only if it is not already set manually (i.e., is still empty)
                if not data[id]['name']:
                    data[id]['name'] = value
            elif detail_type == 'operator':
                data[id]['operator'] = value
            elif detail_type == 'work_area':
                data[id]['work_area'] = value

            # Update existing records for this ID
            for record in data[id]['records']:
                if detail_type != 'name':  # Don't overwrite manually updated names
                    record[detail_type] = value

            print(f"Updated {detail_type} for {id}: {value}")
    save_processed_equipment_data(data)

def update_details_from_old(operator_id, equipment_id, work_area_id, time, hours, last_update_date):
    data = get_processed_equipment_data()

    # Check if equipment_id exists, if not initialize it
    if equipment_id not in data:
        ensure_data_entry(equipment_id)

    # Proceed with updating the details
    existing_record = next((r for r in data[equipment_id]['records'] if r['hours'] == hours), None)
    if existing_record:
        # Update the existing record if the new one has more recent hours
        if int(hours) > int(existing_record['hours']):
            existing_record['time'] = time
            existing_record['hours'] = hours
            data[equipment_id]['last_updated'] = last_update_date
    else:
        # Create a new record without changing the equipment name
        entry = {
            'time': time,
            'hours': hours,
            'name': data[equipment_id]['name'],  # Keep existing name, do not overwrite
            'operator': data[operator_id]['operator'] if operator_id in data else '',
            'work_area': data[work_area_id]['work_area'] if work_area_id in data else ''
        }
        data[equipment_id]['records'].append(entry)
        data[equipment_id]['last_updated'] = last_update_date

    # Save data back to shelve
    save_processed_equipment_data(data)

    # Debugging print statement to verify the saved data
    print(f"After saving: Equipment ID {equipment_id}, Last Updated: {data[equipment_id]['last_updated']}")

# Process .OLD files to update time and hours
def process_old_file(file):
    print("Processing .OLD file...")
    filename = os.path.basename(file.filename)  # Get the base filename without directory paths
    last_update_date = filename.split('.')[0]  # Extract the date from filename, assuming format like 20240215.OLD

    # Ensure the extracted value is exactly 8 characters (YYYYMMDD)
    if len(last_update_date) == 8 and last_update_date.isdigit():
        for line in file.stream:
            line = line.decode('utf-8').strip()
            match = re.match(r'"(.*?)","(.*?)","(.*?)","(.*?)","(.*?)","(.*?)"', line)
            if match:
                operator_id, equipment_id, work_area_id, time, _, hours = match.groups()
                ensure_data_entry(equipment_id)  # Ensure the entry for equipment ID is created before updating
                update_details_from_old(operator_id, equipment_id, work_area_id, time, hours, last_update_date)
    else:
        print(f"Warning: The filename '{filename}' does not match the expected format (YYYYMMDD.OLD)")

@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file uploads and process them."""
    global progress
    progress = 0  # Reset progress
    folder = request.files.getlist('folder')
    total_files = len(folder)

    for i, file in enumerate(folder):
        filename = file.filename
        if filename.endswith('.OLD'):
            process_old_file(file)
        elif filename.endswith('r.n'):
            process_n_files(file, 'name')
        elif filename.endswith('c.n'):
            process_n_files(file, 'work_area')
        elif filename.endswith('e.n'):
            process_n_files(file, 'operator')

        # Update progress
        progress = int(((i + 1) / total_files) * 100)

    return redirect(url_for('main_page'))

@app.route('/upload_progress')
def upload_progress():
    """Return the current progress of the upload."""
    global progress
    return jsonify({'progress': progress})


@app.route('/processed_data', methods=['GET'])
def display_processed_data():
    """ Display processed data as JSON. """
    data = get_processed_equipment_data()
    result_data = []
    for equipment_id, details in data.items():
        if details['records']:
            # Find the record with the highest hours
            latest_record = max(details['records'], key=lambda r: int(r['hours']))
            if latest_record['name']:  # Only add records with a non-empty name
                result_data.append({
                    'equipment_id': equipment_id,
                    'name': latest_record['name'],
                    'hours': latest_record['hours'],
                    'registration_number': details.get('registration_number', ''),
                    'next_service_hours': details.get('next_service_hours', ''),
                    'last_updated': details.get('last_updated', 'N/A')  # Include last updated date
                })
    return render_template('processed_data.html', result_data=result_data)

@app.route('/equipment/<equipment_id>/edit', methods=['POST'])
def edit_equipment(equipment_id):
    data = get_processed_equipment_data()
    if equipment_id not in data:
        return "Equipment not found", 404

    # Extract data from the form
    new_name = request.form.get('new_name')
    service_interval = request.form.get('service_interval')
    registration_number = request.form.get('registration_number')
    current_hours = request.form.get('current_hours')

    # Update equipment details
    if new_name:
        data[equipment_id]['name'] = new_name
    if service_interval:
        data[equipment_id]['service_interval'] = service_interval
    if registration_number:
        data[equipment_id]['registration_number'] = registration_number
    if current_hours:
        latest_record = max(data[equipment_id]['records'], key=lambda r: int(r['hours']), default=None)
        if latest_record:
            latest_record['hours'] = current_hours

    # Save updated data
    save_processed_equipment_data(data)

    return redirect(url_for('equipment_details', equipment_id=equipment_id))



@app.route('/login', methods=['GET', 'POST'])
def login():
    """ Login route to ask for password """
    if request.method == 'POST':
        entered_password = request.form.get('password')
        if entered_password == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('main_page'))
        else:
            return render_template('login.html', error="Incorrect password, please try again.")
    return render_template('login.html')

@app.before_request
def require_login():
    """ Redirect to login if user is not logged in """
    allowed_routes = ['login']
    if 'logged_in' not in session and request.endpoint not in allowed_routes:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    """ Logout route to clear session """
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def main_page():
    data = get_processed_equipment_data()
    warning_list = []
    service_hours_threshold = get_threshold()  # Retrieve current threshold

    for equipment_id, details in data.items():
        latest_record = max(details['records'], key=lambda r: int(r['hours']), default=None)
        if latest_record and details.get('next_service_hours'):
            hours_left = int(details['next_service_hours']) - int(latest_record['hours'])
            weeks_to_service = hours_left / (10.5 * 7)
            if hours_left <= service_hours_threshold:  # Filter equipment within the threshold
                warning_list.append({
                    'equipment_id': equipment_id,
                    'name': details['name'],
                    'registration_number': details.get('registration_number', 'N/A'),
                    'next_service_hours': details['next_service_hours'],
                    'current_hours': latest_record['hours'],
                    'weeks_to_service': round(weeks_to_service, 2),
                    'last_updated': details.get('last_updated', 'N/A')  # Ensure last updated is passed to the HTML
                })

    # Debugging print statement to verify what is in warning_list
    for equipment in warning_list:
        print(f"Main Route: Equipment ID: {equipment['equipment_id']}, Last Updated: {equipment['last_updated']}")

    print(warning_list)  # Check what's inside this list
    print(service_hours_threshold)  # Ensure this has a sensible value

    return render_template('main_screen.html', warning_list=warning_list, service_hours_threshold=service_hours_threshold)

@app.route('/import_data', methods=['GET'])
def import_data():
    """ Serve the import data page where users can upload folders. """
    return render_template('main.html')

def get_threshold():
    with shelve.open('settings.db') as db:
        return db.get('service_hours_threshold', 50)  # Default to 50 if not set

def save_threshold(threshold):
    with shelve.open('settings.db', writeback=True) as db:
        db['service_hours_threshold'] = threshold

@app.route('/settings', methods=['GET'])
def settings():
    current_threshold = get_threshold()
    return render_template('settings.html', current_threshold=current_threshold)

@app.route('/save_settings', methods=['POST'])
def save_settings():
    try:
        threshold = int(request.form['threshold'])
        save_threshold(threshold)
        flash('Settings updated successfully!', 'success')
    except ValueError:
        flash('Invalid input for threshold. Please enter a valid number.', 'error')
    return redirect(url_for('settings'))

@app.route('/equipment/<equipment_id>', methods=['GET', 'POST'])
def equipment_details(equipment_id):
    data = get_processed_equipment_data()
    if equipment_id not in data:
        return "Equipment not found", 404

    details = data[equipment_id]

    if request.method == 'POST':
        # Update details with form data
        next_service_hours = request.form.get('next_service_hours')
        notes = request.form.get('notes')

        if next_service_hours:
            details['next_service_hours'] = next_service_hours
        if notes:
            details['notes'] = notes
        save_processed_equipment_data(data)

    # Get the latest record to show current details
    latest_record = max(details['records'], key=lambda r: int(r['hours']), default=None)
    return render_template('equipment_details.html', equipment_id=equipment_id, details=details, latest_record=latest_record)

@app.route('/equipment/<equipment_id>/serviced', methods=['POST'])
def equipment_serviced(equipment_id):
    data = get_processed_equipment_data()
    if equipment_id not in data:
        return "Equipment not found", 404

    details = data[equipment_id]
    service_date = request.form.get('service_date')

    if not service_date:
        return "Service date is required", 400

    # Get the latest record
    latest_record = max(details['records'], key=lambda r: int(r['hours']), default=None)

    if latest_record:
        hours_at_service = latest_record['hours']
        if details.get('service_interval'):
            # Update next service hours based on interval
            details['next_service_hours'] = str(int(hours_at_service) + int(details['service_interval']))

        # Add service history
        if 'service_history' not in details:
            details['service_history'] = []

        details['service_history'].append({
            'service_date': service_date,
            'hours_at_service': hours_at_service,
            'next_service_hours': details['next_service_hours']
        })

    save_processed_equipment_data(data)
    return redirect(url_for('equipment_details', equipment_id=equipment_id))

@app.route('/equipment/<equipment_id>/manual_next_service_hours', methods=['POST'])
def manual_next_service_hours(equipment_id):
    data = get_processed_equipment_data()
    if equipment_id not in data:
        return "Equipment not found", 404

    details = data[equipment_id]
    manual_next_service_hours = request.form.get('manual_next_service_hours')

    if manual_next_service_hours:
        details['next_service_hours'] = manual_next_service_hours

    save_processed_equipment_data(data)
    return redirect(url_for('equipment_details', equipment_id=equipment_id))


@app.route('/equipment/<equipment_id>/delete_record', methods=['POST'])
def delete_service_record(equipment_id):
    data = get_processed_equipment_data()
    if equipment_id not in data:
        return "Equipment not found", 404

    record_index = int(request.form.get('record_index'))
    if 'service_history' in data[equipment_id] and 0 <= record_index < len(data[equipment_id]['service_history']):
        del data[equipment_id]['service_history'][record_index]

    save_processed_equipment_data(data)
    return redirect(url_for('equipment_history', equipment_id=equipment_id))

@app.route('/equipment/<equipment_id>/history', methods=['GET'])
def equipment_history(equipment_id):
    data = get_processed_equipment_data()
    if equipment_id not in data:
        return "Equipment not found", 404

    details = data[equipment_id]
    service_history = details.get('service_history', [])
    return render_template('equipment_history.html', equipment_id=equipment_id, service_history=service_history)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))


