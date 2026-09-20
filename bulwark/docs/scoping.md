# Scope: what an assessor will look at

Scoping is the single decision that most changes the cost of a CMMC assessment. Everything inside
the boundary is assessed. Everything outside has to be *demonstrably* outside.

## The five asset categories

Bulwark records one of these on every asset, following the CMMC Level 2 scoping guidance.

**CUI assets** process, store or transmit CUI. Engineering workstations, the file server holding
job folders, the cloud tenant where drawings arrive. Assessed against every applicable requirement.

**Security protection assets** provide a security function for the CUI environment, whether or not
they touch CUI themselves: the firewall, the VPN concentrator, the MSP's remote monitoring agent,
the SIEM. Assessed against the requirements relevant to the security function they perform.

**Contractor risk managed assets** are not intended to handle CUI and are governed by policy rather
than assessed against every requirement. The quality lab tablet that runs inspection checklists and
is prohibited from handling CUI. You must be able to show the policy and that it is enforced.

**Specialized assets** are government property, internet-of-things and operational technology,
restricted information systems and test equipment. The CNC controllers on the shop floor belong
here. They are documented in the asset inventory and the system security plan, and you show how
they are protected, but they are not assessed against every requirement.

**Out-of-scope assets** cannot process, store or transmit CUI and are physically or logically
separated from the CUI environment. The marketing laptop on the guest network. Record *why* for
each one: "on the guest VLAN with no route to the enclave and no CUI access" is a rationale; "it's
just marketing" is not.

## How to narrow the boundary

A smaller boundary is cheaper to assess and cheaper to defend.

1. **Decide where CUI is allowed to live**, and make everywhere else a place it is not.
2. **Separate the network.** Put shop-floor machines, guest wireless, cameras and printers on their
   own VLANs with explicit rules into the CUI enclave. A flat network puts everything in scope.
3. **Put CUI in one place.** One document library in a compliant tenant beats drawings scattered
   across email, desktops and USB drives.
4. **Write the rationale down as you go.** Bulwark asks for a rationale on every specialized and
   out-of-scope asset, and prints them in section 4 of the system security plan.
5. **Keep the inventory honest.** An agent creates an asset the moment it reports, flagged for
   review. Categorise it: an uncategorised asset defaults to CUI and widens your scope.

## Specialized assets in a machine shop

Shop-floor equipment is where small suppliers get stuck. A CNC controller may run an unpatchable
Windows build, have no room for an agent, and be unsupported by its vendor for security updates.

What an assessor wants to see is not a perfect machine but a documented, deliberate arrangement:

- The machine is on an isolated VLAN reachable only from the CUI enclave, not from the internet.
- Programs are transferred by a controlled route and deleted at the end of the job, so no CUI sits
  on the machine at rest.
- Removable media used with it is issued, encrypted and inventoried.
- The arrangement, the residual risk and the compensating controls are written into the SSP.

Record that in the asset's rationale and the relevant requirement narratives, and it stops being a
finding and starts being a control.

## External providers

Anything your managed service provider or a cloud service does for you still has to be done, and
you still have to prove it. Record each provider and fill in the responsibility matrix, one row per
requirement. Inheritance is only real when the provider's authorization boundary actually covers
your CUI at the right impact level. See [shared-responsibility.md](shared-responsibility.md).
