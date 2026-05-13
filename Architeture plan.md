Current instalations : 
1.Phyton 
2.Ollama (Check the models that are installed )
3.Cluade
4.- **Screen capture**: `mss` library 
5) Pillow
6) pytesseract
7) Tesseract 5
8) pynput
9) pygetwindow
10) pywin32 
11) chromadb
12) sqlalchemy
13) pyautogui
14) pyperclip
15) pystray
16) plyer
17) google-api-python-client
18) google-auth-oauthlib
19) pydantic
20) toml
21) loguru
22) httpx
U can go ahead and also check if other stuff is installed too 

Hardware constaraint : 
Laptop with : 
1.RTX 3060 6GB VRAM
2.i7 11TH gen 
3.16GB RAM

Limitation / Rules : 
Before writing any code, explain the logic of how you will handle memory management between the OCR engine and the LLM to avoid crashing my 6GB VRAM GPU." This forces the AI to think about your specific hardware limits before it suggests a heavy model. To make sure the application can run constantly in the background without hindering the users front end performance 

If u are unsure of the implemention or any part of the program or exucation It is ok to admit it and ask for clraifcations or ask / give suggestions 

Avoid rushing threw multiple parts of the program in one shot before checking and ensuring funcnality of prevouse part go step by step focusing and fiing and bringging things to a working stage 


Current Phase : Fixing and deubging existing issues 
The program idea was to create a application that constantly looked at the screen to create notes to obsidian based on the context on the screen right now , when a application or a form is dedected aks permision to fill out the necssary details , when a hotkey is pressed ablity to look at the dates on screen and update and create a event on google callender , constant intravel based screen monitoring  , review and recall of and recalled based note takeing on previouse notes or context to ling related content 

But in relaity what was occomplised is : 
1)  Current situation of the context based note taker : The notes taker is not linked to any obsidian and hold on to old first time taken screen shot only and creates only very short notes togther with a speel of useless text not regrading the situation and based on the old context 
    What to fix for the note taker : First make it take a screen shot of the current active location .Make sure it reads the whole context first then . Make it create a summary or expanation and label or sperate out any marked or highlighted content followed by it creating a note in the obsidian valute "C:\Users\nagun\OneDrive\Omniscient Observer" in markdown format and make it link related files in a hyper link format and name the file with the a name based on the content it is looking at 

2) Current situation of The application filler : It  used to work well in dedcting when a application or a form was on screen and see what field it could fill out and matched but never was able to propely implement it where it could fill out the information 
    Where to fix for application filer : Make sure the deduction owwrks again and when it does make it prompt the user with a notification and hotkey based system to allow it to fill . If it is hard to make it simulate mouse movement as done in claude co work and stuff we can create a simpler method of auto fix like where it copys the infomration for the filed we have clicked on to our clip board  

3) Current situation on calender even creater : The program was made me create a auth id for it and link it but idk how the testing and if or not it is working currently 

    Where to fix for calender : First check the current funconlity and make sure it can also read the screen to recogonice dates and allow the user to name it or edit the event before it is commited to google callender make sure it coommits to a diffrent calender like lets say claudes claender inside the google callender 
4) Current situation on intreval based screen monitoring : As far as my knowladge i dont think this is working or has been implemented yet 

 Wher to fix for intereval based screen monitoring : First check if current dependencys are enough for it to work rn then make it check like 1 fps or lower based on how much of hit it does to the performance of the system and allow it to do the same of looking at the whole context and anylizing what is beging down and check what was being down the last time or the succequent hours too see it is a unproductive task that has been runing for a long amount of time or if it is a productive work appricate the user on thier work and tell them to keep going at it wiht a context based apprication 

 5) Implement long term memory linking to this and make it log how long i have been workig on one skill like a skill log and allow it to see to it like a skill tree kinda thing where we mesure how long and the inerlinking skills of the same branch and document it so the user can feel appriciated for the wrk they have done 




Current Action Plan or ressultion needed :
1) Look at the current phase and anylize the current situation of the program and what is happening in it and what is the work that need to be done  
2) After anylizing and findhing what tasks need to be done go over them and break them down as sub goals and reson out how u will solve them or fix them and what are possible problems or allternate ways to do them better looking at thier pros and cons to go back and forth with urself and the user to find the best possible plan of action  
3) Look at other implentions like screen pipe or cowork or simular implementations of this idea to genrate better or look at how they solved these issues or what type of applications they made 
4) After completion of activitys and the owrk always create a true to current situation text on whats going on whats all installed whats acutaly working based on ur own testing and usser input and ideas as such 