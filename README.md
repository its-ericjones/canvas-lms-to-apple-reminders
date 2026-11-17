# Canvas LMS to Apple Reminders using RemCTL

Turn your Canvas LMS calendar feed into Apple Reminders.

`canvas_to_reminders.py` downloads your Canvas iCal feed, finds the assignments that are still upcoming, and creates a reminder for each one using [RemCTL](https://github.com/viticci/remctl), a command-line tool for Apple Reminders. It remembers what it has already added, so you can run it as often as you like without creating duplicates.

## Features

- Reads a Canvas iCal (`.ics`) feed from a URL or a local file
- Creates one reminder per upcoming assignment, using the Canvas event title as the reminder title
- Sets the due date, and keeps all-day assignments as all-day reminders
- Converts timed events from UTC to your local time zone
- Adds the Canvas link to the reminder's notes
- Skips anything already added, tracked by Canvas's permanent event ID (survives title edits)
- Dry run by default; nothing is created until you pass `--apply`
- Keeps your private feed URL in a `.env` file, out of the code

## Requirements

- macOS 14 or later (a RemCTL requirement)
- [RemCTL](https://github.com/viticci/remctl) installed and set up. Run `remctl doctor` to confirm its permissions are in place
- Python 3.9 or later
- Python packages: `requests`, `icalendar`, `python-dotenv` (listed in `requirements.txt`)

## Setup

1. Clone the repo and create a virtual environment:

   ```bash
   git clone https://github.com/its-ericjones/ics-to-remctl.git
   cd ics-to-remctl
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Get your Canvas calendar feed URL. In Canvas, open **Calendar**, then **Calendar Feed** (at the bottom of the right-hand sidebar), and copy the link.

3. Create a `.env` file in the same folder as the script:

   ```
   CANVAS_ICAL_URL="https://your-school.instructure.com/feeds/calendars/user_XXXX.ics"
   ```

   > **Keep this URL private.** It contains a token that gives anyone who has it read access to your Canvas calendar. Add `.env` to your `.gitignore` and never commit it.

4. Create a list in the Reminders app for your assignments. The script uses a list named `Canvas` by default.

## Usage

Preview what would be created (the default; nothing is changed):

```bash
python3 canvas_to_reminders.py
```

Create the reminders:

```bash
python3 canvas_to_reminders.py --apply
```

Options:

| Option | Description |
| --- | --- |
| `--apply` | Actually create reminders. Without it, the script only prints what it would do. |
| `--list NAME` | Reminders list to add to. Default: `Canvas`. |
| `--file PATH` | Read a local `.ics` file instead of the feed URL. Handy for testing. |
| `--state PATH` | Where to keep the "already added" record. Default: `~/.canvas_reminders_state.json`. |

When it finishes, the script prints a summary such as `created: 13 | already added: 0 | failed: 0`.

## How it works

1. **Fetch and parse.** The feed is downloaded and every event is read with the `icalendar` library.
2. **Normalize dates.** Canvas uses plain dates for most assignments and UTC timestamps for others. Timed events are converted to local time; plain dates stay all-day.
3. **Filter.** Only events due today or later are kept.
4. **Skip duplicates.** Each event's Canvas ID is checked against the state file.
5. **Create.** For each new event, the script runs `remctl add -d <due> -l <list> --url <link> -- "<title>"`. The ID is saved only after RemCTL succeeds, so failed events are retried on the next run.

### Finding `remctl`

The script looks for `remctl` in this order:

1. `REMCTL_PATH` in your `.env` file (for example `REMCTL_PATH="/Users/you/bin/remctl"`)
2. Anywhere on your `PATH`
3. `~/bin/remctl`

If none of these finds it, the script stops with a message telling you what to do.

## Running it from Apple Shortcuts

1. In Shortcuts, create a new shortcut and add a **Run Shell Script** action.
2. Set the shell to `zsh` and use full paths to your venv's Python and the script:

   ```bash
   /path/to/ics-to-remctl/.venv/bin/python /path/to/ics-to-remctl/canvas_to_reminders.py --apply 2>&1 || true
   ```

3. Leave **Run as Administrator** unchecked. Running as root changes your home folder and breaks RemCTL's access to your Reminders.
4. Optionally add **Show Notification** with the **Shell Script Result** as its text.

`2>&1` includes error messages in the result, and `|| true` stops Shortcuts from aborting before the notification, so you can read any error.

## Configuration notes

- **Time zone.** Set by `LOCAL_TZ` near the top of the script (default `America/Los_Angeles`). Change it to your own IANA time zone name.
- **Reminder titles.** The full Canvas title is used, including the course bracket, for example `Chapter 18 [BUS.-201-OLH-CRN96393]`.
- **Start over.** If you delete the created reminders and want them re-added, delete the state file too, or the script will consider them already done.

## Limitations

- Existing reminders are never updated. If a due date changes in Canvas, the reminder keeps the old one.
- Reminders are not marked complete when you submit an assignment.
- Tags are not set. Apple's public Reminders APIs do not support tags. RemCTL can write them through private APIs (`--private`), which Apple can change in any macOS release, so this project leaves them out.
- Past events are ignored, so assignments already overdue when you first run the script won't be added.

## Credits

Built on [RemCTL](https://github.com/viticci/remctl) by Federico Viticci.
