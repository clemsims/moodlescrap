class colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def welcome():

    # 1. Clear the console
    # 2. Print the welcome message

    import os
    os.system('cls' if os.name == 'nt' else 'clear')

    print(colors.HEADER)
    print("      _____                    .___.__              ")
    print("     /     \   ____   ____   __| _/|  |   ____      ")
    print("    /  \ /  \ /  _ \ /  _ \ / __ | |  | _/ __ \     ")
    print("   /    Y    (  <_> |  <_> ) /_/ | |  |_\  ___/     ")
    print("   \____|__  /\____/ \____/\____ | |____/\___  >    ")
    print("           \/                   \/           \/     ")
    print("  _________                                         ")
    print(" /   _____/ ________________  ______   ___________  ")
    print(" \_____  \_/ ___\_  __ \__  \ \____ \_/ __ \_  __ \ ")
    print(" /        \  \___|  | \// __ \|  |_> >  ___/|  | \/ ")
    print("/_______  /\___  >__|  (____  /   __/ \___  >__|    ")
    print("        \/     \/           \/|__|        \/        ")
    print(colors.ENDC)
