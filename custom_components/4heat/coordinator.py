"""Provides the MYPV DataUpdateCoordinator."""
from datetime import timedelta
import logging
import socket

from async_timeout import timeout
from homeassistant.util.dt import utcnow
from homeassistant.const import CONF_HOST
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN, SOCKET_BUFFER, SOCKET_TIMEOUT, SOCKET_TIMEOUT_RETRIES, TCP_PORT, DATA_QUERY,
    ERROR_QUERY, RESULT_ERROR, CONF_MODE, MODES, MODE_TYPE, ERROR_TYPE
)

_LOGGER = logging.getLogger(__name__)


class FourHeatDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching 4heat data."""

    def __init__(self, hass: HomeAssistantType, *, config: dict, options: dict, id: str):
        """Initialize global 4heat data updater."""
        self._host = config[CONF_HOST]
        self._mode = False
        self._update_is_active = False
        self.swiches = [MODE_TYPE]
        self.stove_id = id
        
        if CONF_MODE in config:
            self._mode = config[CONF_MODE]

        if self._mode == False:
            self._on_cmd = MODES[0][0]
            self._off_cmd = MODES[0][1]
            self._unblock_cmd = MODES[0][2]
            self.swiches.append(ERROR_TYPE)
        else:
            self._on_cmd = MODES[1][0]
            self._off_cmd = MODES[1][1]
            self._unblock_cmd = MODES[1][2]

        self._next_update = 0
        self.model = "Basic"
        self.serial_number = "1"
        self.last_successful_data = None
        self.timeout_count = 0
        update_interval = timedelta(seconds=60)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from 4heat."""
        def _query_stove(query) -> list[str]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(SOCKET_TIMEOUT)
                s.connect((self._host, TCP_PORT))
                s.send(query)
                result = s.recv(SOCKET_BUFFER).decode()
                
                result = result.replace("[","")
                result = result.replace("]","")
                result = result.replace('"',"")
                d = result.split(",")

                return d
            finally:
                try:
                    s.close()
                except: pass

        def _update_data() -> dict:
            """Fetch data from 4heat via sync functions."""
            list = _query_stove(DATA_QUERY)
            dict = self.data
            if dict == None:
                dict = {}
            if len(list) > 0:
                if list[0] == RESULT_ERROR:
                    list = _query_stove(ERROR_QUERY)
                    
                for data in list:
                    if len(data) > 3:
                        dict[data[1:6]] = [int(data[7:]), data[0]]
            return dict

        try:
            if self._update_is_active:
                _LOGGER.warning(f"Returning stale data while waiting for an active update to finish")
                return self.last_successful_data
            else:
                self._update_is_active = True
                async with timeout(SOCKET_TIMEOUT + 5):
                    d = await self.hass.async_add_executor_job(_update_data)
                    self.last_successful_data = d
                    self.timeout_count = 0
                    self._update_is_active = False

                    return d
        except socket.timeout as error:
            _LOGGER.error(f"Socket timeout: {error}")
            self._next_update = 5
            self._update_is_active = False

            if self.last_successful_data is None:
                return None
            
            if self.timeout_count < SOCKET_TIMEOUT_RETRIES:
                self.timeout_count += 1
            else:
                _LOGGER.error(f"Socket timeouted {SOCKET_TIMEOUT_RETRIES} times in a row")
                self.last_successful_data = None
            
            return self.last_successful_data
        except socket.error as error:
            _LOGGER.error(f"Socket error: {error}")
            self._next_update = 5
            self._update_is_active = False
            raise UpdateFailed(f"Failed to connect: {error}") from error
        except Exception as error:
            self._next_update = 5
            self._update_is_active = False
            raise UpdateFailed(f"Unexpected error: {error}") from error

    async def async_turn_on(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self._host, TCP_PORT))
            s.send(self._on_cmd)
            s.recv(SOCKET_BUFFER).decode()
            s.close()
            _LOGGER.debug("Toggle ON")
        except Exception as ex:
            _LOGGER.error(ex)

    async def async_turn_off(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self._host, TCP_PORT))
            s.send(self._off_cmd)
            s.recv(SOCKET_BUFFER).decode()
            s.close()
            _LOGGER.debug("Toggle OFF")
        except Exception as ex:
            _LOGGER.error(ex)

    async def async_unblock(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self._host, TCP_PORT))
            s.send(self._unblock_cmd)
            s.recv(SOCKET_BUFFER).decode()
            s.close()
            _LOGGER.debug("Toggle Unblock")
        except Exception as ex:
            _LOGGER.error(ex)


    async def async_set_value(self, id, value) -> bool:
        val = str(value).zfill(12)
        set_val = f'["SEC","1","B{id}{val}"]'.encode()
        _LOGGER.debug(f"Command to send: {set_val}")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(SOCKET_TIMEOUT)
            s.connect((self._host, TCP_PORT))
            s.send(set_val)
            s.recv(SOCKET_BUFFER).decode()
            s.close()
            _LOGGER.debug("Set value")
        except Exception as ex:
            _LOGGER.error(ex)

