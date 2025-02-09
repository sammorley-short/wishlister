import yagmail


def send_test_email():
    send_email("Hello from Python", "This is a test email sent using Python.")


def send_email(subject, contents):
    app_password = get_email_app_password()
    email_address = get_email_address()
    yag = yagmail.SMTP(email_address, app_password)
    yag.send(to=email_address, subject=subject, contents=contents)


def get_email_address():
    # Read the app password from the file
    with open("secrets/EMAIL_ADDRESS.txt", "r") as file:
        return file.read().strip()  # Remove any trailing newline or spaces


def get_email_app_password():
    # Read the app password from the file
    with open("secrets/EMAIL_APP_PASSWORD.txt", "r") as file:
        return file.read().strip()  # Remove any trailing newline or spaces


if __name__ == "__main__":
    send_test_email()
