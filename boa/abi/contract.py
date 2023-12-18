import warnings
from collections import Counter
from functools import cached_property
from itertools import groupby
from os.path import basename
from typing import Optional

from _operator import attrgetter
from eth.abc import ComputationAPI
from eth_abi import decode

from boa.abi.function import ABIFunction, ABIOverload
from boa.environment import Address, Env
from boa.util.exceptions import (
    BoaError,
    StackTrace,
    _handle_child_trace,
    strip_internal_frames,
)


class _EvmContract:
    """
    Base class for ABI and Vyper contracts.
    """

    def __init__(
        self,
        env: Optional[Env] = None,
        filename: Optional[str] = None,
        address: Optional[Address] = None,
    ):
        self.env = env or Env.get_singleton()
        self._address = address  # this is overridden by subclasses
        self.filename = filename

    def stack_trace(self, computation: ComputationAPI):
        raise NotImplementedError

    def handle_error(self, computation) -> None:
        try:
            raise BoaError(self.stack_trace(computation))
        except BoaError as b:
            # modify the error so the traceback starts in userland.
            # inspired by answers in https://stackoverflow.com/q/1603940/
            raise strip_internal_frames(b) from None

    @property
    def address(self) -> Address:
        return self._address


class ABIContract(_EvmContract):
    """
    A contract that has been deployed to the blockchain.
    We do not have the Vyper source code for this contract.
    """

    def __init__(
        self,
        name: str,
        functions: list["ABIFunction"],
        address: Address,
        filename: Optional[str] = None,
        env=None,
    ):
        super().__init__(env, filename=filename, address=address)
        self._name = name
        self._functions = functions

        for name, functions in groupby(self._functions, key=attrgetter("name")):
            functions = list(functions)
            fn = functions[0] if len(functions) == 1 else ABIOverload(functions)
            fn.contract = self
            setattr(self, name, fn)

        self._address = Address(address)

    @cached_property
    def method_id_map(self):
        return {function.method_id: function for function in self._functions}

    def marshal_to_python(self, computation, abi_type: list[str]):
        """
        Convert the output of a contract call to a Python object.
        :param computation: the computation object returned by `execute_code`
        :param abi_type: the ABI type of the return value.
        """
        if computation.is_error:
            return self.handle_error(computation)

        decoded = decode(abi_type, computation.output)
        return [_decode_addresses(typ, val) for typ, val in zip(abi_type, decoded)]

    def stack_trace(self, computation: ComputationAPI):
        calldata_method_id = bytes(computation.msg.data[:4])
        if calldata_method_id in self.method_id_map:
            function = self.method_id_map[calldata_method_id]
            msg = f"  (unknown location in {self}.{function.full_signature})"
        else:
            # Method might not be specified in the ABI
            msg = f"  (unknown method id {self}.0x{calldata_method_id.hex()})"

        return_trace = StackTrace([msg])
        return _handle_child_trace(computation, self.env, return_trace)

    @property
    def deployer(self):
        return ABIContractFactory(self._name, self._functions)

    def __repr__(self):
        file_str = f" (file {self.filename})" if self.filename else ""
        return f"<{self._name} interface at {self.address}>{file_str}"


class ABIContractFactory:
    """
    Represents an ABI contract that has not been coupled with an address yet.
    This is named `Factory` instead of `Deployer` because it doesn't actually
    do any contract deployment.
    """

    def __init__(
        self, name: str, functions: list["ABIFunction"], filename: Optional[str] = None
    ):
        self._name = name
        self._functions = functions
        self._filename = filename

    @classmethod
    def from_abi_dict(cls, abi, name: Optional[str] = None):
        if name is None:
            name = "<anonymous contract>"

        functions = [
            ABIFunction(item, name) for item in abi if item.get("type") == "function"
        ]

        # warn on functions with same name
        for function_name, count in Counter(f.name for f in functions).items():
            if count > 1:
                warnings.warn(
                    f"{name} overloads {function_name}! overloaded methods "
                    "might not work correctly at this time",
                    stacklevel=1,
                )

        return cls(basename(name), functions, filename=name)

    def at(self, address) -> ABIContract:
        """
        Create an ABI contract object for a deployed contract at `address`.
        """
        address = Address(address)

        ret = ABIContract(self._name, self._functions, address, self._filename)

        bytecode = ret.env.vm.state.get_code(address.canonical_address)
        if not bytecode:
            raise ValueError(
                f"Requested {ret} but there is no bytecode at that address!"
            )

        ret.env.register_contract(address, ret)

        return ret


def _decode_addresses(abi_type: str, decoded: any) -> any:
    if abi_type == "address":
        return Address(decoded)
    if abi_type == "address[]":
        return [Address(i) for i in decoded]
    return decoded
