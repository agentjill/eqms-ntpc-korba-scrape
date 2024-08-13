# eqms-ntpc-korba-scrape
Script to scrape NTPC Korba EQMS data

## Getting Started

These instructions will help you set up the project on your local machine.

### Prerequisites

- Python 3.12 or higher
- Git (Optional)
- `config.toml` file (Provided separately)

### Installation

1. Clone the repository
#### Option 1: Using Git
```
git clone https://github.com/agentjill/eqms-ntpc-korba-scrape.git
cd project-name
```
#### Option 2: Manual Download

If you don't have Git installed, you can manually download the project:

- Go to the project's GitHub page: https://github.com/agentjill/eqms-ntpc-korba-scrape.git
- Click on the "Code" button and select "Download ZIP"
- Extract the ZIP file to your desired location
- Open a terminal/command prompt and navigate to the extracted folder:

2. Create a virtual environment
```
python -m venv venv
```

3. Activate the virtual environment
- On Windows:
  ```
  venv\Scripts\activate
  ```
- On macOS and Linux:
  ```
  source venv/bin/activate
  ```

4. Install required packages
```
pip install -r requirements.txt
```

5. Place the `config.toml` file in the project root directory

> **Note:** The `config.toml` file is essential for the program to run correctly. Make sure you have received this file separately and placed it in the correct location before running the program.


## Usage

1. Ensure the `config.toml` file is in the project root directory

2. Start the program by executing following in the console.
```
python main.py
```

3. The program will begin executing. To stop the program at any time, press the 'Esc' key.

>**Note:** Make sure you're in the project directory and your virtual environment is activated before running the program.