# Use a lightweight Python image with Alpine as the base
FROM python:alpine3.12

# Set the working directory in the container
WORKDIR /app

# Copy the application files into the container
COPY . /app

# Install Flask and other dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Set environment variables
# We don't neccesary need FLASK_APP and FLASK_RUN_PORT in this case, but we stick to the lecture example.
ENV FLASK_APP=app.py
ENV FLASK_RUN_PORT=5001
ENV API_KEY=w1sLxL3bAN8PgoQY9wap0w==2RArL5FHfhmGgxe1

# Expose port 5001 for the Flask application
EXPOSE 5001

# Command to start the Flask application
CMD ["flask", "run", "--host=0.0.0.0"]
