from pathlib import Path
from setuptools import setup, find_packages


HERE = Path(__file__).parent.absolute()
with (HERE / 'README.md').open('rt') as fh:
    LONG_DESCRIPTION = fh.read().strip()


REQUIREMENTS: dict = {
    'core': [
        'dataclasses',
        'numpy',
        'matplotlib',
        'pandas',
        'requests',
        'scipy',
        'scikit-learn',
        'torch',
        'torchvision',
    ],
    'test': [
        'pytest',
    ],
}


setup(
    name='sops-anomaly',
    description='Anomaly detection algorithms for telemetry data',
    maintainer='Pawel Budzynski',
    maintainer_email='pawel.budzynski19@gmail.com',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    license='MIT',
    packages=find_packages(),
    python_requires='~=3.6',
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    install_requires=REQUIREMENTS['core'],
    extras_require={
        **REQUIREMENTS,
        'all': [req for reqs in REQUIREMENTS.values() for req in reqs],
    },
)