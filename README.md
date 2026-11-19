# Hospital Management API

FastAPI and MongoDB service for managing hospital records. Start it with:

```bash
uvicorn app:app --reload
```

Set `MONGODB_URI` and `MONGODB_DATABASE` in the environment (or `.env`) to
configure MongoDB. Defaults are `mongodb://localhost:27017` and
`hospital_management`. Interactive API documentation is available at
`/docs`. Copy `.env.example` to `.env` to get started with the local defaults;
replace them with your Atlas settings if needed.
The MongoDB connection uses Certifi's trusted CA bundle for TLS certificate
verification.

## Desktop app

Launch the Tkinter desktop interface with:

```bash
python desktop_app.py
```

The desktop app connects directly to the configured MongoDB database and
provides searchable create, read, update, and delete screens for all seven
collections. It does not require the FastAPI server to be running.

For MongoDB Atlas, verify that the cluster is running, the URI is the current
Atlas connection string, and the machine running the API is allowed in the
cluster's Network Access IP access list. A TLS handshake failure or a
`503` from `/` indicates the API cannot connect to MongoDB; do not disable
TLS to work around it.

All collection endpoints support create (`POST`), list (`GET`), read by ID
(`GET /{id}`), full replacement (`PUT /{id}`), and delete (`DELETE /{id}`):

| Resource | Collection endpoint |
| --- | --- |
| Patients | `/patients` |
| Doctors | `/doctors` |
| Appointments | `/appointments` |
| Medical records | `/medical-records` |
| Prescriptions | `/prescriptions` |
| Treatments | `/treatments` |
| Billing records | `/billing` |

List endpoints accept a `limit` from 1 to 100. Appointments, prescriptions,
treatments, and billing records can also be filtered by `patient_id` and
`doctor_id`; doctors can be filtered by `specialization`, and medical records
by `patient_id`. Treatment status can also be changed with
`PATCH /treatments/{treatment_id}/status`, and patients can be assigned to
doctors with `POST /doctors/{doctor_id}/assign-patient/{patient_id}`.
