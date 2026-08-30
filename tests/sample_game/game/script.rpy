# Sample Ren'Py script for testing the extractor.

define e = Character("Eileen", color="#c8ffc8")
define m = Character("[mc_name]")
define narrator = Character(None)
default mc_name = "Daichi"

label start:
    "It was a quiet evening at the apartment."
    e "Hello, [mc_name]. You're home late again."
    m "Sorry. Work has been brutal."
    e happy "Don't worry about it. {b}Dinner{/b} is ready."

    "Sylvie" "Oh, you have a visitor?"

    menu:
        "What do you do?"
        "Hug her":
            e "That's sweet of you."
        "Apologize again":
            m "I really am sorry."

    e "Goodnight." with dissolve
    return

screen quit_dialog():
    text _("Are you sure you want to quit?")
    textbutton _("Yes")
    textbutton _("No")
