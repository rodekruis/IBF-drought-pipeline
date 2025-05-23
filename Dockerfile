FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y libexpat1 
# install ODBC Driver for SQL Server
RUN deps='curl gnupg gnupg2' && \
	apt-get update && \
	apt-get install -y $deps
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
	curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
	apt-get update && \
	ACCEPT_EULA=Y apt-get install -y msodbcsql18
RUN pip install poetry

# clean up
RUN set -ex apt-get autoremove -y && \
    apt-get clean -y && \
    rm -rf /var/lib/apt/lists/*

# add credentials and install drought pipeline
WORKDIR .
COPY pyproject.toml poetry.lock /
RUN poetry config virtualenvs.create false
RUN poetry install --no-root --no-interaction
COPY droughtpipeline /droughtpipeline
#COPY data_updates /data_updates
#COPY tests /tests
COPY config /config
# Create the target directories inside the container
RUN mkdir -p /data/input /data/output 
#COPY data /data
COPY "drought_pipeline.py" .
#COPY "run_scenario.py" .

# ENTRYPOINT ["poetry", "run", "python", "-m", "drought_pipeline"]