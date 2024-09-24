from setuptools import setup, find_packages

setup(
    name='your_package_name',  # Replace with your package name
    version='0.1',
    packages=find_packages(),
    install_requires=[
        'snowflake-connector-python',
        'snowflake-snowpark-python',
        # other dependencies
    ],
)
