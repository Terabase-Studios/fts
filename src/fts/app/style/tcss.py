css = '''
#chatbox {
    border: hkey $panel-lighten-3;
    background: $boost;
    height: 1fr;
    width: 1fr;
    overflow-y: auto;
}

#chatbar {
    height: 4;
    width: 1fr;
    margin-top: 1;
    padding: 0 1 1 1;
}

#chatsend {
    width: 6;
    min-width: 5%;
}

#chatinput {
    background: $boost;
    width: 1fr;
}

#contactpanel{
    height: 1fr;
}

#contactbuttonbar {
    height: 3;
    width: 1fr
}

#contactscroll {
}

#addcontact {
    width: 50%;
    min-width: 25%
}

#removecontact {
    width: 50%;
    min-width: 25%
}

AddContact {
    align: center middle;
}

#addcontactcontainer {
    height: 11;
    width: 100;
    border: vkey $success;
}

#addcontactfinal {
    margin-left: 1;
    width: 50%;
}

#cancelcontactadd {
    margin-right: 2;
    width: 50%;
}

RemoveContact {
    align: center middle;
}

#removecontactcontainer {
    height: 8;
    width: 100;
    border: vkey $error;
}

Horizontal {
   width: 1fr;
   height: 1fr;
   layout: horizontal;
   overflow: hidden hidden;
}

Vertical {
    background: 0%;
}


#toprow {
    height: 60%;
    background: $surface;

}

#toprowa {
    width: 25%;
    height: 1fr;
    border: vkey $secondary-lighten-1;

}

#toprowb {
    border: vkey $secondary-lighten-1;

    width: 50%;
}

#toprowc {
    width: 25%;
    height: 1fr;
    border: vkey $secondary-lighten-1;
}


#bottomrow {
    background: $surface;
    border: hkey $secondary;
    height: 40%;
}

#bottomrowa {
  width: 50%;
  border: vkey $secondary;

}

#bottomrowb {
  width: 50%;
  border: vkey $secondary;
}

#requests_label{
    width: 100%;
    height: 1;
    min-height: 1;
    content-align: center middle;
}

#requests_scroll {
    height: 1fr;
    width: 100%;
}

#requests_header {
    min-height: 4;
    height: 4;
}

Request {
    height: 12;
    border: hkey $panel-lighten-3;
    background: $boost 100%;
}

#request_button_bar{
    height: Auto;
    width: 100%;
}

#request_accept{
    width: 50%;
}

#request_deny{
    width: 50%;
}

#request_log{
    overflow-y: hidden;
    overflow-x: auto;
    height: 1fr;
    background: $surface-lighten-2 100%;
    padding: 1;
    outline: outer $surface-lighten-1;
    scrollbar-background: $surface;
}

#requests_container{
   background: $boost 0%;
}

FileSelector {
    height: 5;
    min-height: 5;
    padding: 0 1 0 1;
    background: $surface;
}

#file_input {
    width: 1fr;
    height: Auto;
    background: $boost;
}

#browse_button {
    width: 10;
    min-width: 10%;
    margin-right: 1;
    height: Auto;
}

ContactSelector {
    width: 1fr;
    height: 5fr;
    padding: 0 2 2 2;
    background: $surface;
}

#contact_selection_list {
    width: 1fr;
    height: 1fr;
    border: hkey $secondary;
    background: $boost;
}

#sending_button_bar{
    width: 1fr;
    padding: 0 2 0 2
}

#select_all_button{
    width: 40%;
    min-width: 10%;
}

#deselect_all_button{
    width: 40%;
    min-width: 10%;
}

#file_send_button{
    width: 20%;
    min-width: 5%;
}

LogEntry, InactiveEntry, ActiveEntry {
    background: $boost;
    outline: wide darkgrey;
    margin: 0 4 0 0;
    min-width: 50;
    padding: 1;
    align: left top;
    min-width: 25%;
    height: Auto;
}

#logtab {
    background: 0%;
    background: $boost;
    overflow-x: auto;
    min-height: 0;
    height: Auto;
}

#logview {
    text-wrap: wrap;
    text-overflow: ellipsis;
    overflow-y: hidden;
    overflow-x: auto;
    height: Auto;
    background: $boost 0%;
}

.error {
    outline: wide $error;
}

.success {
    outline: wide $success;
}

InactiveEntry, ActiveEntry {
    outline: wide $primary;
    height: Auto;
}

ActiveEntry {
    outline: wide $accent;
}

#inactive_entry {
    padding: 1;
}

#active_container, #inactive_container {
    height: Auto;
}

#inactive_bar {
    height: Auto;
    width: 100%;
}

#cancel_entry {
    width: 8;
    min-width: 8;
    min-height: 0;
    align: right middle;
}










LibraryTree {
    border: tall $accent-darken-3;
    background: $boost;
    padding-left: 1;
    height: auto;
}

.TreeTab {
    border: hkey $accent-darken-2;
    padding: 1;
    margin: 1;
    background: $boost;
}

#library_search {
    border: hkey $panel;
    background: $boost;
    margin: 0 1 0 1;
}

LibraryPanel {
    width: 20%;
    padding: 1;
    border: tall $secondary-lighten-2;
    background: $boost-lighten-2;
}

LibraryTreeDisplay {
    width: 80%;
    background: $boost;
    border: tall $secondary-lighten-2;
}

#library_refresh {
    width: 1fr;
}

#library_switch_text{
    text-align: center;
    text-style: bold;
    width: 1fr;
    margin-bottom: 1;
}

#library_switch {
    width: 1fr;
    height: auto;
}

#library_help_text{
    text-overflow: fold;
    width: 1fr;
    height: 1fr;
    margin: 0;
    padding: 0;
}


#notepad {
    border: tall $secondary-lighten-2;
    width: 100%;
}

#notepad_export {
    margin: 1 2 1 2;
    width: 1fr;
}
'''