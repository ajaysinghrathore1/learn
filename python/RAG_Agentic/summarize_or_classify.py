import streamlit as st
# from langchain.document_loaders import PyPDFLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
# from langchain.llms import OpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain.docstore.document import Document
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import sqlite3

## send mail
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import pandas as pd
import tempfile
import os
import sys

import pywhatkit
# pip install twilio
from twilio.rest import Client


sys.path.append(r"C:\genai\Code\stremlit")  # Adjust the path as needed
from mainclass import MainClass
main_class = MainClass() 

llm = main_class.model()

labels = "Politics, Sports, Finance, Technology ,Positive, Neutral, Negative ,English, French, Hindi"

template = """
Classify the following text into one of the categories: {labels}

Text: "{text}"

Answer with only the label.
"""
prompt = PromptTemplate(
    input_variables=["text", "labels"],
    template=template
)
chain = LLMChain(llm=llm, prompt=prompt)

database_path = r"C:\genai\dataset\my_database.db"
# Initialize session state for the text area if not already present
if 'user_text' not in st.session_state:
    st.session_state.user_text = ""

### Define  functions 
def clear_text_area():
    """Clears the content of the text area."""
    st.session_state.user_text = ""

def create_get_sqlite(): 
    """create a sqlite connection and return connection """
    con = sqlite3.connect(database_path, timeout=60)
    return con

def create_table():
    """create a sqlite table if not exists and return connection """
    sql_text ="""CREATE TABLE IF NOT EXISTS tbl_message (
    id rowid,
    sent_date TIMESTAMP,
    message NVARCHAR(500)
    );"""
    con = create_get_sqlite()
    cursor = con.cursor()
    result =cursor.execute(sql_text)    
    con.close()
    

def save_message_to_table( message :str) :
    """insert the message and date time of the message to sqlite table """
    sql_text =f"""insert into tbl_message( sent_date , message ) values(current_timestamp,"{message}" ) """
    print(sql_text)
    
    create_table()
    con = create_get_sqlite()
    cursor = con.cursor()
    result =cursor.execute(sql_text)
    con.commit()
    print("Data inserted successfully.")
    con.close()


def send_message_to_whatsapp( message :str):
    # phone_number = "+919811518340"  # Include country code
    # message = "Hello from Python!"
    # pywhatkit.sendwhatmsg_instantly(phone_number, message)

    
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    client = Client(account_sid, auth_token)
    message = client.messages.create(
        from_='whatsapp:+14155238886',
        body = message ,
        to='whatsapp:+919811518340'
        )

    
    
def send_sms_to_phone(message :str):
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    client = Client(account_sid, auth_token)
    message = client.messages.create(
        from_='+1111111111' ,    #twillio phone number for sms
        body= message ,
        to='+919111111111'   ##Sender phone number
        )
    print(message.sid)    



def generate_message_4_sms_twitter(text : str , word_limit :int) :
    # Custom Prompt
    custom_prompt = PromptTemplate(
        input_variables=["text","word_limit"],
        template="""
    You are an expert summarizer. Summarize the following text in under {word_limit} words:
    {text}
    """
    )
    
    chain = load_summarize_chain(llm,  prompt=custom_prompt)
    
    summary_output = chain.run({"input_documents": [text], "word_limit": word_limit})
    st.markdown("summary for sms/twitter")  
    st.markdown(summary_output)  
    send_sms_to_phone(summary_output)
    return 
    

def email_message(summary :str):
    # Define the subject and body of the email.
    subject = "summarize of text/doc" if selected_option=="summarize"  else "classify of text/doc"
    body = summary   #"This is the body of the text message"
    sender = "sendermail@gmail.com"         # Define the sender's email address.
    recipients = ["dummy1@gmail.com", "dummy2@gmail.com"]  # List of recipients to whom the email will be sent.   
    password = "oxxx0xxx0xx0xx"           # Password for the sender's email account.
    # Create a MIMEText object with the body of the email.
    msg = MIMEText(body)
    # Set the subject of the email.
    msg['Subject'] = subject
    # Set the sender's email.
    msg['From'] = sender
    # Join the list of recipients into a single string separated by commas.
    msg['To'] = ', '.join(recipients)

    # Connect to Gmail's SMTP server using SSL.
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp_server:
        # Login to the SMTP server using the sender's credentials.
        smtp_server.login(sender, password)
        # Send the email. The sendmail function requires the sender's email, the list of recipients, and the email message as a string.
        smtp_server.sendmail(sender, recipients, msg.as_string())
    # Print a message to console after successfully sending the email.
    print("Message sent!")

def save_and_send_messages(summary : str , actual_text:str ,selected_option_dict :dict):
    if selected_option=="summarize"  :
        
        if selected_option_dict[0] :    #    "save data to SQLite"
            save_message_to_table(summary)
        if selected_option_dict[1] :    #    "Send message to Whatsapp"
            send_message_to_whatsapp(summary)
        if selected_option_dict[2] :    #    "Text message to Phone"
            send_sms_to_phone(summary)
        if selected_option_dict[3] :    #    "Send a email"
            email_message(summary)
        if selected_option_dict[4] :    #    "Send message to Twitter/X" 
            generate_message_4_sms_twitter(actual_text , 50)        
        print("save and send the messages sucessfully ")
    else:
        save_message_to_table(summary)


def select_send_message_option(summary : str , actual_text:str):
    data_df = pd.DataFrame(
        {
            "send option": ["save data to SQLite", "Send message to Whatsapp", "Text message to Phone", "Send a email" ,"Send message to Twitter/X"],
            "defaul_selected_option": [True, False, False, False , False],
        }
    )

    selected_option= st.data_editor(
        data_df,
        column_config={
            "favorite": st.column_config.CheckboxColumn(
                "Message to be send?",
                help="Select your **defaul_selected_option** widgets",
                default=False,
            )
        },
        disabled=["widgets"],
        hide_index=True,
    )
    if st.button("Submit"):  
        selected_option_dict = selected_option.to_dict()["defaul_selected_option"] 
        save_and_send_messages(summary  , actual_text , selected_option_dict)


##**************************************************************************************************
## streamlit 
##**************************************************************************************************
st.title("summarize, or classify")

# Define the options for the radio buttons
options = ["summarize", "classify"]

# Create the radio button widget
selected_option = st.radio("Choose task type:", options 
                        ,captions=[
        "Summarized the upload text or manual entry text.",
        "classify the upload text or manual entry text."
                ],)

input_option = ["Manual", "File Upload"]
input_selected_option = st.radio("Choose entry option:", input_option)

if input_selected_option =="Manual" :
    text_input = st.text_area("Enter or copy paste the text, for execution press ctrl+Enter " , key="user_text")

    summary =""
    spinner_text = "summarize" if selected_option=="summarize"  else "classify"
    if text_input is not None  and len(text_input.strip()) > 10 :
        with st.spinner(f"⏳ Processing file and {spinner_text}..."):
            if selected_option=="summarize"  :  ### Summarizing 
                chain = load_summarize_chain(llm, chain_type="stuff")
                docs = Document(page_content=text_input)
                summary = chain.run([docs])  # ✅ works        
                # summary = chain.run(text_input)
                select_send_message_option(summary ,docs)
                st.success("✅ Summary generated:")
            else:
                summary = chain.run(text=text_input, labels=labels)
                print("Prediction:", summary)
                select_send_message_option(summary)
                st.success("✅ classification generated:")
            # st.markdown(f"<div style='font-size:18px; color:darkgreen; font-weight: 500;'>summary</div>",  unsafe_allow_html=True )        
            st.markdown(summary)   


else:
    uploaded_file = st.file_uploader("Upload Source File", type=["txt" ,"pdf"], key="file_upload")

    if uploaded_file is not None:
        spinner_text = "summarize" if selected_option=="summarize"  else "classify"
        with st.spinner(f"⏳ Processing file and {spinner_text}..."):

            file_type = uploaded_file.name.split(".")[-1]

            # Handle PDF
            if file_type == "pdf":
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name

                loader = PyPDFLoader(tmp_path)
                documents = loader.load()

            # Handle TXT
            elif file_type == "txt":
                text = uploaded_file.read().decode("utf-8")
                documents = [Document(page_content=text)]
            if selected_option=="summarize"  :  ### Summarizing 
                # Split the document
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
                docs = text_splitter.split_documents(documents)

                # Summarize using LangChain chain
                chain = load_summarize_chain(llm, chain_type="map_reduce")
                summary = chain.run(docs)

                # Clean up temp file
                if file_type == "pdf":
                    os.remove(tmp_path)

                st.success("✅ Summary generated:")
                st.markdown("summary")  
                st.text_area("📄 Summary", summary, height=300)
                select_send_message_option(summary ,docs)

            else:
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
                docs = text_splitter.split_documents(documents)
                summary = chain.run(text=docs, labels=labels)
                
                st.success("✅ classification generated:")
                st.text_area("📄 Text/pdf classification", summary, height=80)              
                select_send_message_option(summary)




