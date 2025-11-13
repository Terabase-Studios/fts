import asyncio

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.validation import Validator, ValidationResult
from textual.widgets import Tree, Button, Input

from fts.app.backend.contacts import get_users, get_contacts, add_contact, remove_contact, \
    get_seen_users, replace_with_contact


class Contacts(Container):
    def compose(self) -> ComposeResult:
        with Vertical(id="contactpanel"):
            with VerticalScroll(id="contactscroll"):
                tree = Tree("Contacts", id="contacttree")
                tree.root.expand()
                self.online_branch = tree.root.add("Online", expand=True)
                self.offline_branch = tree.root.add("Offline", expand=True)
                self.widget_tree = tree
                yield tree

            with Horizontal(id="contactbuttonbar"):
                yield Button("Add contact", variant="success", id="addcontact")
                yield Button("Remove contact", variant="error", id="removecontact")

    async def on_mount(self):
        # Initial population
        await reload_contacts(self.widget_tree, self.online_branch, self.offline_branch)

        # Auto-refresh every 5 seconds
        async def refresh_loop():
            while True:
                await asyncio.sleep(1)
                await reload_contacts(self.widget_tree, self.online_branch, self.offline_branch)

        asyncio.create_task(refresh_loop())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        if event.button.id == "addcontact":
            self.app.push_screen(AddContact(), self.handle_add_input)

        elif event.button.id == "removecontact":
            self.app.push_screen(RemoveContact(), self.handle_remove_input)

    def handle_add_input(self, result: tuple[str, str] | None):
        if result:
            add_contact(result[0], result[1])
            reload_contacts(self.widget_tree, self.online_branch, self.offline_branch)  # update tree immediately

    def handle_remove_input(self, result: str | None):
        if result:
            remove_contact(result)
            reload_contacts(self.widget_tree, self.online_branch, self.offline_branch)  # update tree immediately


async def reload_contacts(tree: Tree, online_node, offline_node):
    # Fetch contacts in a background thread
    contacts = await asyncio.to_thread(get_users) or {}

    # Preserve expanded state
    online_expanded = online_node.is_expanded
    offline_expanded = offline_node.is_expanded

    # Clear old leaves (synchronous)
    for child in list(online_node.children):
        child.remove()
    for child in list(offline_node.children):
        child.remove()

    # Add new leaves (synchronous)
    for contact in contacts.get("online", []):
        online_node.add_leaf(contact)
    for contact in contacts.get("offline", []):
        offline_node.add_leaf(contact)

    # Restore expanded state (synchronous)
    if online_expanded:
        online_node.expand()
    else:
        online_node.collapse()

    if offline_expanded:
        offline_node.expand()
    else:
        offline_node.collapse()

class AddContact(ModalScreen[tuple[str, str] | None]):
    """Modal for adding a contact.
       Returns (name, ip) or None if cancelled."""

    def compose(self) -> ComposeResult:
        with Container(id="addcontactcontainer"):
            with Vertical():
                yield Input(
                    placeholder="Contact Name",
                    id="addcontactname",
                    validators = [Blank(), IsNotAlreadyContact()]
                )
                yield Input(
                    placeholder="Contact Ip",
                    id="addcontactip",
                    suggester=SuggestFromList([i for i in get_seen_users() if replace_with_contact(i) not in get_contacts()], case_sensitive=True),
                    validators=[Blank(), IsNoncontactUser()]
                )
                with Horizontal(id="addcontactbuttonbar"):
                    yield Button("add", variant="success", id="addcontactfinal")
                    yield Button("cancel", variant="error", id="cancelcontactadd")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name_input = self.query_one("#addcontactname", Input)
        ip_input = self.query_one("#addcontactip", Input)

        if event.button.id == "addcontactfinal":
            # return the tuple (name, ip)
            results = name_input.validate(name_input.value).is_valid
            results = results and ip_input.validate(ip_input.value).is_valid
            if results:
                self.dismiss((name_input.value, ip_input.value))

        elif event.button.id == "cancelcontactadd":
            self.dismiss(None)


class RemoveContact(ModalScreen[str | None]):
    """A modal screen for removing a contact.
       Returns the contact string, or None if cancelled."""

    def compose(self) -> ComposeResult:
        with Container(id="removecontactcontainer"):
            with Vertical():
                yield Input(
                    placeholder="Contact Name",
                    id="removecontactname",
                    suggester=SuggestFromList(get_contacts(), case_sensitive=True),
                    validators=[CheckContact()],
                )

                with Horizontal(id="addcontactbuttonbar"):
                    yield Button("remove", variant="error", id="addcontactfinal")
                    yield Button("cancel", variant="success", id="cancelcontactadd")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        input_widget = self.query_one("#removecontactname", Input)

        if event.button.id == "addcontactfinal":
            results = input_widget.validate(input_widget.value)

            # Check if *all* validators passed
            if results.is_valid:
                self.dismiss(input_widget.value)

        elif event.button.id == "cancelcontactadd":
            # Return None if cancelled
            self.dismiss(None)



class CheckContact(Validator):
    def validate(self, value: str) -> ValidationResult:
        if self.is_contact(value):
            return self.success()
        else:
            return self.failure("Contact not found!")

    @staticmethod
    def is_contact(value: str) -> bool:
        return value in get_contacts()

class Blank(Validator):
    def validate(self, value: str) -> ValidationResult:
        """Check a string is equal to its reverse."""
        if self.is_not_empty(value):
            return self.success()
        else:
            return self.failure("Contact not found!")

    @staticmethod
    def is_not_empty(value: str) -> bool:
        return not value == ""

class IsNoncontactUser(Validator):
    def validate(self, value: str) -> ValidationResult:
        if self.is_user(value):
            return self.success()
        else:
            return self.failure("Value is not an user!")

    @staticmethod
    def is_user(value: str) -> bool:
        users = [i for i in get_seen_users() if replace_with_contact(i) not in get_contacts()]
        return value in users

class IsNotAlreadyContact(Validator):
    def validate(self, value: str) -> ValidationResult:
        if not self.is_contact(value):
            return self.success()
        else:
            return self.failure("Contact already exists!")

    @staticmethod
    def is_contact(value: str) -> bool:
        contacts = get_contacts()
        return value in contacts