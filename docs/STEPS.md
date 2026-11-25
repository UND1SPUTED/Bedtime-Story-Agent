# Steps: run, test, and publish on GitHub

This guide covers the commands for Windows PowerShell, run from the project folder. The Mac/Linux equivalents are shown where they differ.

---

## Part 1: Set up

1. **Install Python 3.9 or newer** from python.org. Tick "Add python.exe to PATH" during installation.
2. **Open the project folder** in VS Code or PowerShell.
3. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   Mac/Linux: `source .venv/bin/activate`
4. **Install the packages:**
   ```powershell
   pip install -r requirements.txt
   ```

**Check:** the prompt starts with `(.venv)`, and the install ends with `Successfully installed`.

---

## Part 2: Test (no API key needed)

```powershell
python -m unittest discover -s tests -v
```

**Check:** the last line says `OK`, and the output lists 43 tests. If any fail, fix them before continuing.

---

## Part 3: Run the web app

1. **Start the server:**
   ```powershell
   python app.py
   ```
   **Check:** the terminal shows `Running on http://127.0.0.1:5000`.
2. **Open** http://127.0.0.1:5000 in your browser.
3. **Save your API key.** Paste the key into the API key box and press **Save key**. The key stays in memory only.
4. **Write a story.** Enter a request (or click an example) and press **Write story**.
   - **Check:** a story, six judge scores, and a verdict appear.
   - **Check:** the counter line shows "Samples in sample_outputs.md: N · this story is Sample N".
5. **Request a change.** Type a change under the story and press **Apply change**.
   - **Check:** the change is logged as a new sample.
6. **Stop the server.** Press **Ctrl+C** in the terminal.

Every story and change is added to `sample_outputs.md` automatically. Aim for 4 to 5 entries across different categories before publishing.

---

## Part 4: Run the terminal version (optional)

```powershell
python main.py
```

Type a request, read the story, and press Enter to finish. Terminal runs do not add to `sample_outputs.md`.

---

## Part 5: Check that no key is in the project

```powershell
Select-String -Path *.py,*.md,*.js,*.html,*.txt -Pattern "sk-ant-api03" -Recurse
```

**Check:** the only match is the placeholder in `tests/test_app.py` or `tests/test_samples.py`, which is not a real key. If a real key appears anywhere, delete it, then create a new key in the Anthropic Console and delete the old one.

---

## Part 6: Create the GitHub repository

1. **Install Git** from git-scm.com if you don't have it. Check with `git --version`.
2. **Set your name and email** (use the email on your GitHub account):
   ```powershell
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
3. **Create an empty repository on GitHub:**
   1. Go to github.com/new.
   2. Name it, for example, `bedtime-story-agent`.
   3. Set it to **Public**.
   4. Do **not** tick "Add a README," ".gitignore," or "license." The project already has them.
   5. Click **Create repository**, and keep the page open.

---

## Part 7: Upload the project

Run these from the project folder, with the virtual environment deactivated or still active (it doesn't matter, because `.venv` is ignored):

```powershell
git init
git add .
git status
```

**Check the `git status` output:** it should list `app.py`, `README.md`, `sample_outputs.md`, `tests/`, `static/`, `templates/`, `docs/`, and similar files. It must **not** list `.venv/`, `.env`, or any `__pycache__` folder. If it does, stop and check that `.gitignore` is in the folder.

Then commit and connect to GitHub (replace the URL with yours from the GitHub page):

```powershell
git commit -m "Bedtime story agent: judge loop, web UI, sample logging"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/bedtime-story-agent.git
git push -u origin main
```

**Authentication:** GitHub no longer accepts your account password for pushes. When `git push` asks for credentials:
- Windows usually opens a browser sign-in window. Sign in and approve it.
- If it asks for a password, create a token at github.com/settings/tokens (classic, with the `repo` scope) and paste it instead of your password.

**Check:** refresh the GitHub page. The files should be listed, and `README.md` should display below the file list.

---

## Part 8: Verify the public repository

1. **Open the repo link in a private (incognito) window.** The repo should load without signing in. If it asks you to sign in, it is still private: go to Settings → General → Change visibility → Public.
2. **Check for secrets.** In the repo, press **t** on the keyboard to open file search, or use the search box, and search for `sk-ant-api03`. The only result should be the placeholder in the tests.
3. **Check the README.** Open `README.md` on GitHub. The block diagram should render as a picture, not as code.

---

## Part 9: Later changes

After editing files, from the project folder:

```powershell
git add .
git commit -m "Describe the change"
git push
```

---

## If something goes wrong

- **`git` not recognized:** install Git and reopen the terminal.
- **`push` rejected with "fetch first":** the GitHub repo has a file the local one doesn't. Only do this if you created the repo with files you don't need: `git pull origin main --allow-unrelated-histories`, then `git push`.
- **A real key was pushed:** delete the key in the Anthropic Console, create a new one, and remove the key from the file with a new commit. Deleting it in a later commit still leaves it in history, so treat the old key as compromised and rotate it.
