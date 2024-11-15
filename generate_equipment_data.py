import shelve

def generate_equipment_data():
    with shelve.open('equipment_data.db', writeback=True) as db:
        if 'processed_equipment_data' not in db:
            db['processed_equipment_data'] = {}

        data = db['processed_equipment_data']

        # Add a few example equipment entries
        data['4800001656B93201'] = {
            'records': [
                {'time': '08:00', 'hours': '120', 'name': 'Excavator 1', 'operator': 'John Doe', 'work_area': 'Site A'},
            ],
            'name': 'Excavator 1',
            'operator': 'John Doe',
            'work_area': 'Site A',
            'next_service_hours': '150',
            'notes': 'Needs oil change soon.',
            'service_interval': '50',
            'service_history': [],
            'registration_number': 'REG1234',
            'last_updated': '20240215'
        }

        data['5300001C38C64001'] = {
            'records': [
                {'time': '12:00', 'hours': '80', 'name': 'Bulldozer', 'operator': 'Jane Smith', 'work_area': 'Site B'},
            ],
            'name': 'Bulldozer',
            'operator': 'Jane Smith',
            'work_area': 'Site B',
            'next_service_hours': '100',
            'notes': '',
            'service_interval': '30',
            'service_history': [],
            'registration_number': 'REG5678',
            'last_updated': '20240215'
        }

        # Manually sync to disk to ensure persistence
        db.sync()

if __name__ == '__main__':
    generate_equipment_data()
