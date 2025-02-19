# Use the official Python image from the Docker Hub
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the Pipfile and Pipfile.lock to the container
COPY Pipfile* ./

# Install pipenv and dependencies from Pipfile
RUN pip install pipenv && pipenv install --deploy --ignore-pipfile

# Copy application code to the container
COPY discordbot.py agent.py ./

# Command to run your bot
CMD ["pipenv", "run", "python", "discordbot.py"]
