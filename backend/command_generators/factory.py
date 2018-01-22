from backend.command_generators.spreadsheet import commands_generator_from_ooxml_file
from backend.command_generators.json import commands_generator_from_native_json

"""
- Parser
  - Receives a stream which contains one or more command_executors, creates one or more instances of command_executors

- CommandsExecutor
  - Receives a Workspace and one or more command instances to be executed

- Command.
  - Can be created directly, by a Parser (different Parsers possible), or by deserialization
  - Serializable/deserializable in: JSON or DataFrame format. Execute. Acting always over a
  - Could have a method to estimate the execution time

- Workspace
  - Can be serialized/deserialized
  - Allows reading, writing, deleting variables
  - Can integrate the result of a Command (if the Command does not have this capability)

"""


def command_generator_parser_factory(generator_type, file_type, file, state):
    """
    Returns a generator appropriate to parse "file" and generate command_executors

    :param generator_type:
    :param file_type:
    :param file:
    :param state: State used to validate existence of some variables at parse time
    :return:
    """
    # TODO Prepare the input stream. It can be a String, a URL, a file, a Stream
    # TODO Define a routine to read it into memory
    s = file
    if generator_type.lower() in ["rscript", "r-script", "r"]:
        # TODO The R script was prepared to be run from outside NIS, using R NIS client
        # TODO Running the script from the inside should be managed slightly different:
        # TODO - Recognize that it is an internally launched script
        # TODO   - The R script will open an interactive session: do not open a new InteractiveSession and
        # TODO   - find a way to reenter the launching Int.Sess.
        # TODO   - ignore open/close session commands creating or saving case studies
        # TODO   - execute commands modifying in memory state, ignore others
        #
        # TODO Take the R script and launch it as a separate process.
        # TODO
        pass
    elif generator_type.lower() in ["python", "python-script"]:
        # TODO Exact same considerations as for R scripts
        pass
    elif generator_type.lower() in ["spreadsheet", "excel", "workbook"]:
        # A sequence of commands, providing the whole case study
        if isinstance(s, bytes):
            pass
        elif isinstance(s, str):
            pass  # TODO It may be a file name

        yield from commands_generator_from_ooxml_file(s, state)
    elif generator_type.lower() in ["json", "native", "primitive"]:  # "primitive" is Deprecated
        # A list of commands. Each command is a dictionary: the command type, a label and the content
        # The type is for the factory to determine the class to instantiate, while label and content
        # are passed to the command constructor to elaborate the command
        if isinstance(s, bytes):
            s = s.decode("utf-8")
        yield from commands_generator_from_native_json(s, state)