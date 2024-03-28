FROM python:3.9

# Install necessary Python packages
RUN pip install boto3 tabulate
RUN apt-get update && apt-get install -y less vim curl unzip sudo

# Install aws cli v2
# Refer to https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2-linux.html for installation guide
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
RUN unzip awscliv2.zip
RUN sudo ./aws/install

# Set the working directory
WORKDIR /app

# Copy scripts to container
COPY . /app

# Execute the script
CMD ["python", "./app.py"]