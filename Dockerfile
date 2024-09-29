# Use the official Python image from the Docker Hub
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the Pipfile and Pipfile.lock to the container
COPY Pipfile* ./

# Install pipenv
RUN pip install pipenv

# Install the dependencies from the Pipfile
RUN pipenv install --deploy --ignore-pipfile

# Copy the rest of your application code to the container
COPY main.py .

# Command to run your bot
CMD ["pipenv", "run", "python", "main.py"]
