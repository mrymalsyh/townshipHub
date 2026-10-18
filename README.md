# Township Hub

A community wellbeing platform for a township: residents report problems and book spaces and items; management sees patterns, closes the loop and checks returns.
Built with **Django + PostgreSQL**. Works in any browser, including phones.

---

## Part 1: Get it running (about 15 minutes)

Do the steps in order. Do not skip any. Words in `grey boxes` are things you type or click.

### Step 0. Install two programs (one time only)

1. **Python 3.10 or newer**: https://www.python.org/downloads/
   - On Windows, tick the box **"Add Python to PATH"** on the first screen of the installer.
2. **PostgreSQL**: https://www.postgresql.org/download/
   - The installer asks you to choose a password for the user `postgres`. **Write it down.** You need it in Step 5.
   - Leave the port as `5432`.

### Step 1. Unzip the project

Unzip `township_hub.zip` somewhere easy, for example the Desktop. You will get a folder called `township_hub`.

### Step 2. Open a terminal inside that folder

- **Windows:** open the folder, click the address bar at the top, type `cmd`, press Enter.
- **Mac:** right-click the folder, choose **New Terminal at Folder**.

### Step 3. Make a private box for the project's tools

Windows:
```
python -m venv venv
venv\Scripts\activate
```
Mac:
```
python3 -m venv venv
source venv/bin/activate
```
You should now see `(venv)` at the start of the line. Whenever you open a new terminal later, run the `activate` line again.

### Step 4. Install the tools

```
pip install -r requirements.txt
```

### Step 5. Make the database

Open **pgAdmin** (it came with PostgreSQL). Log in with your password, right-click **Databases**, choose **Create > Database**, name it `township`, press Save.

(Or in the terminal: `psql -U postgres -c "CREATE DATABASE township;"`)

### Step 6. Tell the project your password

Make a copy of the file `.env.example` and name the copy `.env` (exactly, with the dot, no `.txt`).
Open `.env` in Notepad and change this one line to your real password from Step 0:

```
DB_PASSWORD=your-postgres-password
```

### Step 7. Build the tables and add demo data

```
python manage.py migrate
python manage.py seed_demo
```

### Step 8. Start it

```
python manage.py runserver
```

Open **http://127.0.0.1:8000** in your browser. 🎉

| Who | Username | Password |
|---|---|---|
| Township manager | `admin` | `admin123` |
| Resident (priority help, Block C) | `aisyah` | `demo123` |
| Other residents | `ravi`, `mei`, `hakim`, `siti`, `john` | `demo123` |

To stop the server press `Ctrl + C`. To wipe and reload the demo data: `python manage.py seed_demo --reset`.

### Show it on your phone (same Wi-Fi)

Run `python manage.py runserver 0.0.0.0:8000`, find your computer's IP address (for example `192.168.1.20`), and open `http://192.168.1.20:8000` on the phone.

---

## Part 2: If something goes wrong

| You see | Do this |
|---|---|
| `password authentication failed` | The password in `.env` is wrong. Fix `DB_PASSWORD`. |
| `database "township" does not exist` | Do Step 5. |
| `permission denied to create extension "btree_gist"` | In `.env` use `DB_USER=postgres` (the main user). |
| `No module named ...` | You forgot `venv\Scripts\activate` (Windows) or `source venv/bin/activate` (Mac). Run it, then Step 4 again. |
| `'python' is not recognized` | Reinstall Python and tick **Add Python to PATH**. On Mac type `python3`. |
| Page has no styling on first load | Refresh once. The font loads from the internet; the page still works without it. |
| The map is grey | It needs internet to load map tiles. Pins still show. |
| Cannot install PostgreSQL right now | Add the line `USE_SQLITE=1` to `.env`. Everything works except the database-level double-booking guard. Switch back before the demo. |

---

## Part 3: The demo story (5 minutes)

Log in as **aisyah** in one browser window and **admin** in another (use a private window for the second).

1. **Resident reports an outdoor problem.** Aisyah: *Report a problem* > choose **Outside** > pick *Central Walkway* > submit. Point out she earned care points.
2. **Neighbours are alerted.** Log in as `siti`: the bell shows an alert, the home page shows a yellow sign, and the **Map** shows the pin. Open it, press **It is still broken**, and add a tip.
3. **The AI sees the pattern.** As **admin**: *AI insights* > **Analyse now**. Block C plumbing (6 reports) is flagged as a likely shared pipe problem. Walkway damage is flagged as "patching is not working". Press **Create upgrade proposal** for a printable evidence page.
4. **Management closes the loop.** Open a report > set status and add **alternative route advice**. Everyone gets it. The resident's **transit-line tracker** moves forward.
5. **Priority for vulnerable residents.** *Reports*: Aisyah's reports are tagged *Priority resident* and sorted higher.
6. **Booking and closures.** *Bookings* > close the Swimming Pool for cleaning. Anyone with a clashing booking (Mei) is notified. Try double-booking the Community Hall: the database refuses it.
7. **Items and returns.** *Items & returns*: check in a returned item as **Damaged**. Stock drops, the resident's care points change, and the projector shows **"Damaged 3 times... Consider REPLACING"**.
8. **Overview.** Manager home shows open reports, resolve rate, average fix time and where problems cluster.

---

## Part 4: What is built

| Feature | Where |
|---|---|
| Indoor (private) and outdoor (public) reports, photo, exact spot | `reports/` |
| Parcel-style progress tracker, public timeline | `templates/reports/detail.html` |
| Outdoor alerts to all residents, public map with pins | `reports/services.py`, `reports/views.py` |
| "Still broken / looks fixed" votes and neighbour tips | `reports/views.py` |
| Official alternative-route advice from management | `reports/services.py` |
| Priority for vulnerable residents | `reports/models.py` (`priority_score`) |
| Hotspot detection and AI conclusions, upgrade proposal | `insights/` |
| Live availability, closures, clash notices | `bookings/` |
| Double-booking blocked inside PostgreSQL | `bookings/models.py` (`ExclusionConstraint`) |
| Items with live stock, loans, overdue | `inventory/` |
| Return grading (OK, needs cleaning, damaged, missing, unused), repair-or-replace advice | `inventory/services.py` |
| Care points for useful reports and careful returns | `accounts/models.py` |
| QR link to report with the place pre-filled | `/reports/new/?location=ID` |

### The AI part, honestly

Hotspots are found with a database query (same place + same problem + several times). The *write-up* uses the Claude API if you put `ANTHROPIC_API_KEY=...` in `.env` and run `pip install anthropic`. Without a key, a built-in rule-based writer produces the conclusions, so the demo never breaks. The page tells you which one wrote each conclusion.

### Not built yet (say this as "roadmap")

Photo AI triage, weather-based warnings, voice and multi-language input, peer-to-peer lending, a real mobile app (the site is already mobile-friendly), email or push notifications (alerts are in-app and refresh every 30 seconds).

---

## Part 5: Where things live

```
township/        settings and the main URL list
accounts/        users, login, register, manager-only pages
core/            places (Location), home page, demo data (seed_demo), tests
reports/         problem reports and everything around them
bookings/        facilities, bookings, closures
inventory/       items, loans, returns
insights/        hotspots, AI write-ups, manager overview
notifications/   bell and alerts
templates/       the HTML pages
static/css/      the one stylesheet
```

Add or edit places, facilities and items at http://127.0.0.1:8000/django-admin/ (log in as `admin`).
Run the automated checks with `python manage.py test`.

Demo coordinates are fictional. Edit them in the admin so pins land on your real township.
