def __version__():
    return "2.5.0-alpha.2"

def colorize_icon(icon: str, version: str) -> str:
    RESET = "\033[0m"

    NAME = "\033[38;2;205;205;205m"
    VERSION = RESET
    LABEL = "\033[38;2;150;150;150m"

    # Define your three RGB constants for the gradient
    COLOR1 = (255, 0, 0)  # top-left (red)
    COLOR2 = (127, 0, 227)  # middle (green)
    COLOR3 = (0, 0, 255)  # bottom-right (blue)

    lines = icon.splitlines()
    height = len(lines)
    width = max(len(line) for line in lines) if lines else 1

    def rgb(r, g, b):
        return f"\033[38;2;{r};{g};{b}m"

    out = []

    for y, line in enumerate(lines):
        new_line = []
        for x, ch in enumerate(line):
            if ch == "█":
                # Normalize position along diagonal
                t = (x + y) / (width + height - 2)  # 0 → 1

                # Interpolate three colors
                if t < 0.5:
                    ratio = t / 0.5
                    r = int(COLOR1[0] * (1 - ratio) + COLOR2[0] * ratio)
                    g = int(COLOR1[1] * (1 - ratio) + COLOR2[1] * ratio)
                    b = int(COLOR1[2] * (1 - ratio) + COLOR2[2] * ratio)
                else:
                    ratio = (t - 0.5) / 0.5
                    r = int(COLOR2[0] * (1 - ratio) + COLOR3[0] * ratio)
                    g = int(COLOR2[1] * (1 - ratio) + COLOR3[1] * ratio)
                    b = int(COLOR2[2] * (1 - ratio) + COLOR3[2] * ratio)

                new_line.append(rgb(r, g, b) + ch + RESET)
            else:
                new_line.append(ch)

        colored = "".join(new_line)

        # Text accents (overlay after gradient)
        if "Terabase's" in colored:
            colored = colored.replace("Terabase's", f"{NAME}Terabase's{RESET}")
        if "FTS-Tool" in colored:
            colored = colored.replace("FTS-Tool", f"{NAME}FTS-Tool{RESET}")
        if f"v{version}" in colored:
            colored = colored.replace(f"v{version}", f"{VERSION}v{version}{RESET}")
        if "▌Graphical" in colored or "Interface▐" in colored:
            colored = colored.replace("▌Graphical", f"{LABEL}▌Graphical{RESET}")
            colored = colored.replace("Interface▐", f"{LABEL}Interface▐{RESET}")

        out.append(colored)

    return "\n".join(out)


XXXX = __version__()
ICON = colorize_icon(f"""                                         
         ██████████████████████              
 ██████  ██                    ██     ██████ 
███████████                      ████████████
███████████                       ███████████
  ██████ ██      Terabase's       ██ ██████  
     ██████       FTS-Tool        ██████     
     ██████        v{XXXX}         ██████     
       ████                       ████       
        ████     ▌Graphical      █████       
         ████    Interface▐     ████         
         █████                 █████         
         ███████             ███████         
         ██ ████             ████ ██         
         ██  █████         █████  ██         
         ██   █████       █████   ██         
         ██    █████     █████    ██         
         ██     █████   █████     ██         
         ██      █████ █████      ██         
          ██████████████████████████         
                   ███████                   
                   ███████                   
                    █████         
""", XXXX)