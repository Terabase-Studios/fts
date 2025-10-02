from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.suggester import SuggestFromList
from textual.validation import Validator, ValidationResult
from textual.widgets import Tree, Button, Input
from textual.screen import ModalScreen

from fts.app.backend.contacts import get_users, get_user_list, get_contacts


class Contacts(Container):
    def compose(self) -> ComposeResult:
        # Active section
        contacts = get_users()

        with Vertical(id="contactpanel"):
            with VerticalScroll(id="contactscroll"):
                tree: Tree[str] = Tree("Contacts", id="contacttree")
                tree.root.expand()
                online = tree.root.add("Online", expand=True)
                offline = tree.root.add("Offline", expand=True)
                for contact in contacts['online']:
                    online.add_leaf(contact)

                for contact in contacts['offline']:
                    offline.add_leaf(contact)

                yield tree

            with Horizontal(id="contactbuttonbar"):
                yield Button("add contact", variant="success", id="addcontact")
                yield Button("remove contact", variant="error", id="removecontact")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        if event.button.id == "addcontact":
            self.app.push_screen(AddContact(), self.handle_add_input)

        elif event.button.id == "removecontact":
            self.app.push_screen(RemoveContact(), self.handle_remove_input)

    def handle_add_input(self, result: tuple[str, str] | None):
        if not result:
            #Todo: call contacts to add
            pass

    def handle_remove_input(self, result: str | None):
        if not result:
            # Todo: call contacts to remove
            pass


class AddContact(ModalScreen[tuple[str, str] | None]):
    """Modal for adding a contact.
       Returns (name, ip) or None if cancelled."""

    def compose(self) -> ComposeResult:
        with Container(id="addcontactcontainer"):
            with Vertical():
                yield Input(
                    placeholder="Contact Name",
                    id="addcontactname",
                    validators = [Blank()]
                )
                yield Input(
                    placeholder="Contact Ip",
                    id="addcontactip",
                    suggester=SuggestFromList(get_user_list(), case_sensitive=True),
                    validators=[Blank()]
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
        """Check a string is equal to its reverse."""
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